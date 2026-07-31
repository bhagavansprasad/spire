# Spire Enhancement — Status Tracker

Tracks progress against `docs/spire_enhancement_requirements.md` v1.1.
That document is the specification; this file is the living record of what
has actually been done. Update this file at the end of any session that
touches a phase — do not edit the requirements doc itself to reflect
progress.

The requirements doc is **not frozen**. New requirements may be added when
they are genuinely new — v1.1 added COL-01 to COL-03 and CSV-01 from SME
feedback. What must not happen is editing it to record progress; that is
this file's job.

This file also holds the **design** for whichever phase is currently
open. Design sections live here while their phase is in progress and are
pruned back to decisions-only once the phase merges — otherwise twelve
phases of design detail bury the status table above them.

**Last updated:** 2026-07-31 (Phase 2A opened — column resolution, P0, SME-raised)

---

## Phase status

| Phase | Requirements | Status | Notes |
|---|---|---|---|
| 0 | (four pre-existing defects, not in the requirements doc) | ✅ Done | Merged. See handoff 2026-07-30 evening. |
| 1 | UX-05, OBS-01, OBS-02 | ✅ Done | Merged in two branches. Design and results below — prune to decisions-only before Phase 2 grows its own section. |
| 2 | UX-01, UX-02, UX-03 | 🟨 UX-01 done | UX-01 merged (`phase-2-refusal-messages`, `phase-2-refusal-tests`). UX-02 (narrowing guidance) and UX-03 (truncation disclosure) not started — **deferred behind 2A**. |
| **2A** | **COL-03, COL-01, COL-02, CSV-01** | 🟨 **Open — P0** | **SME-raised 2026-07-31, measured same day.** Requested columns silently dropped. Discovery in §G. Nothing built yet. |
| 3 | OBS-03, OBS-04, OBS-05 | ⬜ Not started | |
| 4 | TST-02, TST-03, TST-01 | ⬜ Not started | |
| 5 | PRF-01 | ⬜ Not started | See "Orthogonal work" below — a related refactor has already happened. |
| 6 | PRF-02, PRF-03 | ⬜ Not started | |
| 7 | PRF-05 | ⬜ Not started | |
| 8 | UX-04, PRF-07, PRF-08 | ⬜ Not started | |
| 9 | API-01, API-02 | ⬜ Not started | |
| 10 | API-03 | ⬜ Not started | Blocked on DEC-02. |
| 11 | PRF-06, PRF-04 | ⬜ Not started | |
| 12 | API-04, API-05 | ⬜ Not started | Blocked on phase 9 and DEC-03. |

## Decisions register

| Decision | Status | Notes |
|---|---|---|
| DEC-01 — planner architecture (KG vs LLM planner) | Open | No new information this session. |
| DEC-02 — external tool exposure model (copilot) | Open | No new information this session. |
| DEC-03 — multi-backend support | Open | No new information this session. |
| *(new, not in the original register)* — `server.py` tool-registration pattern | Open | `core.py` + domain-grouped `register_*.py` files, imported by `server.py` for side effect, proposed and not yet approved. Not a DEC-number in the spec; tracked here because it blocks the `server.py` maintainability split, not because it blocks a requirement. |
| *(new)* — OBS-01 flag count | **Closed** | Stays at the spec's six flags, plus the `show_all` convenience OBS-01 explicitly permits. Two extra flags were proposed and **rejected**: progress lines and the summary footer are always required, so they are not gated at all. No amendment to the frozen spec is needed. |
| *(new)* — UX-05 literal deviation | **Closed, accepted** | Progress and summary print on every run, which contradicts UX-05's wording. Resolved by stream separation rather than by amending the spec — see §D3. |

---

## Orthogonal work (not requirements-doc phases)

Maintainability refactors, done outside the phase sequence, on explicit
request. Recorded here so nobody mistakes them for phase progress.

- **`synthesizer.py`**: 3,056 → 491 lines, split into 9 sibling files.
  Done, merged, verified token-identical against the pod.
- **`planner.py`**: 1,764 → 439 lines, split into 6 sibling files. Done,
  merged, verified token-identical against the pod.
- **`po_lifecycle.py`** (993 lines): mapped into four layers, external
  contract enumerated. Not extracted — parked.
- **`server.py`** (1,052 lines): mapped, 33 tools across five domain
  groups. Needs the registration-pattern decision above before any code.

**Relevant adjacency:** PRF-01 ("deterministic response construction
across all shapes") will be easier to implement now that response
building lives in per-domain modules rather than one large file. This is
a side effect of the refactor, not progress on PRF-01 itself.

---

## Baseline numbers (do not re-derive without saying so)

From `docs/spire_enhancement_requirements.md` §3, measured 2026-07-29,
unchanged by anything done so far:

| Metric | Value |
|---|---|
| Mean wall-clock per answered prompt | 16.0 s |
| Mean total tokens per prompt | 12,230 |
| Parse input tokens per prompt | 8,667 mean (superseded — see below) |

**Superseded by Phase 0 (2026-07-30):** parse input tokens moved to a
range, **~8,805–8,819**, varying with question length, after the risk-only
parser fix added ~140 tokens to the lifecycle parse prompt. This is the
only number Phase 0 or either refactor changed. PRF-07/PRF-08 targets
should still be read against the original 16.0s / 12,230-token baseline
until a phase touches performance directly.

---
---

# Phase 1 design — UX-05, OBS-01, OBS-02

**Status: complete. Both branches merged.**

Requirements covered: UX-05 (quiet default output), OBS-01 (independent
per-component verbosity flags), OBS-02 (configuration precedence).

**The goal in one sentence:** make diagnostics controllable — off by
default, switched on per component when you need them.

## D1. Discovery — what actually prints

Measured against the real tree, not uploaded files.

**226 `print(` sites total.** The split matters more than the total.

| Bucket | Sites | In scope? |
|---|---|---|
| Standalone dev/verify tools | 149 | **No** — `try_po_lifecycle.py` (54), three `verify_*.py` (55), `print_kg.py` (13), `rebuild_kg.py` (9), `score_parser_prompts.py` (8), `test_kg_connection.py` (5), `draw_graph.py` (1), `inspect_trace.py` (4). Not the answer path; UX-05 says nothing about them. |
| `run_prompt_set.py` | 35 | **No** — see §D3. It is a regression harness, not a user-facing entry point. |
| User-facing runners | 27 | **Yes** — `run_graph.py` (25), `ask.py` (2). |
| Library code under `src/` | 11 | **Yes** — see below. |
| Library, already env-gated | 2 | **No** — both in `pipeline.py`'s `_maybe_save_png`, gated on `SPIRE_GRAPH_PNG`, dev-only. |

**The 11 in-scope library sites:**

| File | Count | What |
|---|---|---|
| `src/spire/config.py` | 4 | 3× `[llm] provider=… model=…` in `build_llm`, 1× `[llm] stage=… in=… out=…` in `log_usage`. All stderr. |
| `src/spire/synthesizer/synthesizer.py` | 1 | `print(f"[debug] shape = {shape}", file=sys.stderr)` — hardcoded, ungated, fires every run. |
| `src/spire/mcp_server/tools/` | 7* | Across `aggregate_purchase_orders.py` (3), `aggregate_invoices.py` (1), `compare_orders_to_invoices.py` (1), `po_lifecycle.py` (1). Tagged `[tool_name] msg` to stderr. |

\* one call site in `aggregate_purchase_orders.py` spans multiple lines;
count is by `print(` occurrence.

**Three findings that shaped the design:**

1. **`display_formatters.py` has zero prints.** Every formatter *returns*
   a string. The presentation layer is already pure and already separate
   from output. This is why Phase 1 is tractable at all, and it is the
   same property API-01 will need.
2. **`run_graph.py` is ungated top to bottom.** Every print is
   unconditional — intent, plan, outputs, synthesized answer, summary,
   token report. There is no verbosity concept to switch off. UX-05
   *introduces* the concept rather than configuring an existing one.
3. **A tagged-stderr convention already exists** in 11 places
   (`[llm]`, `[graph]`, `[po_lifecycle]`, `[compare_orders_to_invoices]`).
   The design formalises it rather than replacing it.

**Incidental finding, unrelated to Phase 1 — now closed.** The handoff
carried "17 tests are DESELECTED by a marker filter nobody has examined"
as an open housekeeping item. It is explained by `pyproject.toml`'s
`addopts = "-m 'not integration'"` plus the `integration` marker: they
are the tests requiring MCP server, Gemini, or the pod, deselected
deliberately. Not a gap. **Struck off the carried-forward list.**

## D2. Mechanism

**stdlib `logging` with named per-component loggers, plus
`pydantic-settings` for the config layer.**

Rejected alternative, recorded because it was recommended and withdrawn:
a hand-rolled `Diagnostics` flags dataclass. The stated objection to
`logging` was that `_format_plan` returns multi-line tables that level
prefixes would mangle. That objection is wrong — a handler with a bare
`%(message)s` formatter passes the block through untouched, one line of
setup. The hand-rolled version would have reimplemented the logger
hierarchy badly.

Also considered: `-v`/`-vv`/`-vvv` counting (too coarse alone; OBS-01
rejects it explicitly, but it is the "convenience flag" OBS-01 permits),
and OpenTelemetry (right answer eventually — OBS-03 and OBS-04 are spans
and OBS-05 is a trace export — but overkill for Phase 1; `logging` keeps
OTel additive at Phase 3 rather than a rewrite).

### Loggers

| Logger | Emits | Gated? |
|---|---|---|
| `spire.parser` | parsed intent, KG menu size, refusal flavor/detail | `show_parser` |
| `spire.planner` | selected plan, tool, arguments, filters | `show_planner` |
| `spire.executor` | per-step raw output | `show_raw_output` |
| `spire.synthesizer` | response object before rendering, shape detection | `show_synthesizer` |
| `spire.tokens` | per-call and end-of-run token counts | `show_tokens` |
| `spire.timings` | per-stage latency — created now, silent until OBS-03 | `show_timings` |
| `spire.progress` | `… progress n/total` events | **never — always on** |
| `spire.summary` | the pipeline counts footer | **never — always on** |

`tokens` and `timings` are cross-cutting: any component emits them, so
they get their own logger rather than being special-cased inside a
component's. One mechanism, no exceptions.

`progress` and `summary` are loggers rather than bare `print()` calls
even though nothing gates them. They cost nothing extra and it means a
future API-01 can silence them by detaching a handler, without touching
call sites.

### Flags

Six from OBS-01, plus the convenience flag OBS-01 permits. **Seven
total.** No addition to the frozen spec.

| Flag | Logger |
|---|---|
| `show_parser` | `spire.parser` |
| `show_planner` | `spire.planner` |
| `show_raw_output` | `spire.executor` |
| `show_synthesizer` | `spire.synthesizer` |
| `show_tokens` | `spire.tokens` |
| `show_timings` | `spire.timings` |
| `show_all` | all six above |

On → that logger at `DEBUG`. Off → `WARNING`. These loggers emit at
`DEBUG` only, so `WARNING` is silence.

`spire.progress` and `spire.summary` sit at `INFO` permanently and are
unaffected by every flag, including `show_all`.

## D3. Two deliberate deviations from UX-05, both accepted

Recorded openly rather than worked around quietly.

### Deviation 1 — progress and summary always print

UX-05's first acceptance criterion says a default invocation prints "the
answer and nothing else." Progress lines and the summary footer print on
every run, so that criterion is not met as literally worded.

**Resolution — stream separation, not a spec amendment:**

| Stream | Carries |
|---|---|
| **stdout** | the answer, and nothing else, ever |
| **stderr** | progress and summary always; the six flagged components when switched on |

This is the `curl` pattern: data on stdout, progress on stderr. Redirect
or pipe stdout and you get the pure answer — which is what UX-05 exists
to protect, and exactly what API-01 needs. UX-05's **third** criterion
("no diagnostic text is written to standard output when flags are off;
diagnostics use a separate stream or logger") is satisfied precisely.

The deviation is in wording, not intent.

### Deviation 2 — `run_prompt_set.py` is not silenced

Quiet-by-default applies to `run_graph.py` and `ask.py` only.

`run_prompt_set.py` runs 31 prompts to prove nothing regressed. Its
output *is* its purpose; silencing it by default would make it useless
for the one job it has. It is a developer harness, not a user-facing
entry point, and UX-05's rationale — demonstration to non-technical
users, and unblocking §8's interfaces — does not apply to it.

Its 35 print sites are untouched by this phase.

### The one uncovered site that does get folded

`(refusal: {flavor} — {detail})` in `run_graph.py` folds into
`show_parser`. Both values come off the parser's `Refusal` object. The
`capability_message(r, menu)` line above it is the **answer** and stays
on stdout unconditionally.

## D4. Configuration precedence (OBS-02)

Later layer wins.

| # | Layer | Where |
|---|---|---|
| 1 | code defaults — **every flag `False`** | `diagnostics.py`. This *is* UX-05. |
| 2 | committed team default | `[tool.spire.diagnostics]` in `pyproject.toml` |
| 3 | personal preference | `SPIRE_SHOW_*` environment variables |
| 4 | this one run | CLI `--show-*` / `--no-show-*` |

OBS-02 specifies only file → CLI and is silent on env. Env is placed
above file and below CLI by convention: the file is the committed
default, env is your machine, CLI is this invocation.

### Why `pyproject.toml` and not `personas.yaml`

`personas.yaml` holds **secrets** — passwords, DSNs — and is gitignored.
`pyproject.toml` holds **non-secret config** and is committed.

One file for both forces a bad choice: commit it and credentials enter
git, or gitignore it and the team's defaults can never be reviewed or
shipped. There is no third outcome. `personas.example.yaml` already in
the tree shows the same split was reached independently.

`personas.yaml` does not grow, shrink, or change in Phase 1.

`[tool.*]` is reserved for exactly this by PEP 518, and
`[tool.pytest.ini_options]` is already in the file. `requires-python =
">=3.11"` means `tomllib` is stdlib — no parser dependency.

**Caveat on record:** `pyproject.toml` is not shipped when a package is
pip-installed. Fine today (runs from `~/pocs/spire`). If API-01 is ever
deployed as an installed package, deployment config must come from env —
which the layering already handles.

### File surface

```toml
[tool.spire.diagnostics]
show_parser = false
show_planner = false
show_raw_output = false
show_synthesizer = false
show_tokens = false
show_timings = false
```

Section absent entirely → all off. That satisfies OBS-02's second
acceptance criterion.

`show_all` is a CLI/env convenience only and is not a file key — writing
`show_all = true` into a committed file would be a way to permanently
defeat UX-05 by accident.

### Env surface

One variable per flag: `SPIRE_SHOW_PLANNER=1`. Free from
`pydantic-settings` via `env_prefix="SPIRE_"`, and consistent with the
existing `SPIRE_LLM_PROVIDER` / `SPIRE_LLM_MODEL` convention in
`config.py`.

A compound `SPIRE_LOG=planner,parser` (the `RUST_LOG` style) is terser
but cannot report an invalid name without hand-written validation — see
below. Deferred as a possible convenience.

### CLI surface

`argparse.BooleanOptionalAction` yields `--show-planner` and
`--no-show-planner` from a single `add_argument`.

**Trap — CLI default must be `None`, not `False`.** With `default=False`,
an unspecified flag is indistinguishable from an explicit
`--no-show-planner`, so the CLI would silently override the file with
`False` on *every* run. OBS-02's first acceptance criterion ("a flag set
true in configuration can be disabled for a single run") would then be
untestable, because config could never be true at runtime. `None` makes
"not specified" distinguishable from "explicitly off".

### Invalid flag names (OBS-02 criterion 3)

`SettingsConfigDict(extra="forbid")` makes an unknown key in the TOML
section raise a `ValidationError` naming the key. Free.

**Not free:** `pydantic-settings` silently ignores unmatched environment
variables. A typo'd `SPIRE_SHOW_PLANER=1` would vanish. This needs an
explicit scan of `os.environ` for the `SPIRE_SHOW_` prefix, checked
against the known field set. Called out because it is the one acceptance
criterion the library does not give us.

## D5. The third-party logger trap

**Never call `logging.basicConfig()`. Never set a level on the root
logger.**

`langchain`, `httpx`, `oracledb` and `fastmcp` all log at `DEBUG`. A
`--show-planner` that flips root to `DEBUG` buries the answer in
third-party output and fails OBS-01's "enabling one flag produces output
from that component only" on the very first run.

Setup:

- One `StreamHandler(sys.stderr)` with `Formatter("%(message)s")` — bare,
  so `_format_plan`'s multi-line tables pass through untouched.
- Attached to the `spire` logger with `propagate = False`, so nothing
  reaches root.
- `spire` at `DEBUG`; each child set per the table in §D2.

## D6. Dependencies

| Package | Status |
|---|---|
| `pydantic-settings` | **Added** (2.14.1). Separate distribution from pydantic v2. In `requirements.txt`. Pulls in `python-dotenv`. |
| `tomllib` | stdlib on 3.11+. Confirmed by `requires-python = ">=3.11"`. |

## D7. Files touched

**New**

- `src/spire/diagnostics.py` — settings model, flag→logger mapping,
  logger setup, env scan.
- `tests/test_diagnostics.py`

**Edited**

- `pyproject.toml` — add `[tool.spire.diagnostics]`
- `requirements.txt` — add `pydantic-settings`
- `src/spire/config.py` — 4 prints → loggers
- `src/spire/synthesizer/synthesizer.py` — 1 print → logger
- `scripts/run_graph.py` — answer to stdout; everything else to loggers
- `scripts/run_prompt_set.py` — **one line**, see the correction below
- `scripts/flag_matrix.sh` — new, see §D11
- `.gitignore` — `t.txt`, `flag_matrix/`

**Removed**

- `scripts/ask.py` — already deprecated. Unrelated to Phase 1, surfaced
  while enumerating entry points, carried on this branch rather than
  given its own: a deletion of dead code cannot regress anything.

**Two corrections to this list, found during the build**

*The 7 tool prints are out of scope.* Every one is a pagination line
emitted beside a `report_progress` call — progress, not component
diagnostics. More decisively, they run in the **MCP server process**,
not the client, so they cannot reach `run_graph.py`'s stdout at all.
In-scope library prints were therefore **5, not 11**: `config.py` ×4 and
`synthesizer.py` ×1.

*`run_prompt_set.py` needed one line after all.* It is not quieted — its
output is its purpose — but without a `setup_diagnostics()` call nothing
installs a handler on the `spire.*` loggers, so the always-on progress
lines would vanish and a slow 31-prompt run would look like a hang. One
call, no flags. The per-call `[llm] stage=...` token echo it used to
show is gone by design; end-of-run totals are unaffected.

**Deliberately not touched**

- `src/spire/mcp_server/tools/*` — the 7 pagination prints, per above
- `personas.yaml` — credentials only, unchanged
- `scripts/display_formatters.py` — already pure, returns strings, prints
  nothing
- `src/spire/graph/pipeline.py` — both prints already env-gated, dev-only
- the 149 dev-tool prints — out of scope

`src/spire/mcp_server/` is touched, so **the MCP server must be restarted**
before any verification run.

## D8. Build order

Two branches. UX-05 and OBS-01 are **one unit**: UX-05's second
acceptance criterion is "diagnostics restorable in full via the flags in
OBS-01", so a branch that only silences output leaves diagnostics
unreachable and the repo in a worse state than it started.

| Branch | Covers | Status |
|---|---|---|
| `phase-1-diagnostic-flags` | UX-05 + OBS-01 | ✅ **Merged.** `diagnostics.py`, logger setup, 5 library prints converted, `run_graph.py` wired, CLI flags. Settable via CLI only at this point, which fully satisfies both requirements. |
| `phase-1-config-precedence` | OBS-02 | ✅ **Merged.** `[tool.spire.diagnostics]`, `pydantic-settings`, the environment layer, the env-name scan. Nothing above `flags_from_args` changed — the new layers slotted in underneath it, and `run_graph.py` needed no edit at all. |

Per-branch sequence follows the standing build order: targeted tests
during work, full suite before any commit touching source, PR-based
merge.

## D9. Verification — as run

All of the below is what actually happened, not what was planned.

**Full suite: 645 passed, 17 deselected, 1 xfailed.** Up from 607; the
38 new ones are `tests/test_diagnostics.py`. That is the new baseline.

**Flag matrix — 67 live runs against the pod.** `scripts/flag_matrix.sh`
ran all 64 combinations of the six flags on
`"What is the risk rating on PO 701337 and why?"`, plus 3 control runs
with no flags.

- **All 67 stdout hashes identical.** No flag alters the answer.
- **The 3 controls agree with each other**, which is what makes that
  meaningful — Gemini is not perfectly deterministic at temperature 0,
  so without a matching control set a single hash would prove nothing.
- **Every flag lit its own component and no other** — OBS-01's core
  acceptance criterion, verified across the whole matrix rather than
  argued from the code.

**Default stderr is exactly the 5-line `Summary:` block.** Nothing
leaked. Confirmed by reading the whole file, not by grepping for known
markers — the marker table alone proves each expected block appeared,
not that nothing unexpected did.

**`--show-timings` is inert, not merely untested.** All 32 pairs of runs
differing only by that flag are byte-identical. The logger exists and is
correctly silent until OBS-03.

**Parse tokens 8,812** — within the ~8,805–8,819 baseline range. Neither
the conversion nor the logger wiring moved them.

**MCP server restarted** before the live runs; `src/spire/` changed.

### Branch 2 (OBS-02)

**Full suite: 672 passed, 17 deselected, 1 xfailed.** Up from 645. The
27 net new tests bring `tests/test_diagnostics.py` to 65.

**All four precedence layers verified live against the pod**, not just
in a constructor:

| Check | Result |
|---|---|
| defaults only | quiet — `Summary:` block alone |
| `[tool.spire.diagnostics]` `show_tokens = true` | token report appears, no flag, no env var |
| `SPIRE_SHOW_PLANNER=1` | plan block appears, nothing on the command line |
| file `true` + `--no-show-tokens` | token report gone — **OBS-02 criterion 1** |

**Both invalid-name paths verified.** A typo'd key in `pyproject.toml`
raises naming `show_planer`; a typo'd `SPIRE_SHOW_PLANER` raises naming
the variable *and* listing the valid ones.

**Tests are hermetic.** An autouse fixture clears every `SPIRE_SHOW_*`
variable and repoints `PYPROJECT_FILE` at a nonexistent path. Without
it a green run would prove something about the developer's shell rather
than about the code.

**Not re-run: `scripts/flag_matrix.sh`.** §D11 says branch 2 is exactly
when to re-run it. Skipped on the argument that the 65 unit tests cover
precedence directly and the four live checks above cover the wiring —
17 minutes and 67 LLM calls for confirmation of something already
demonstrated. Recorded as a judgement call, not an oversight.

**Not run:** the 31-prompt lifecycle set. `run_prompt_set.py` is
substantively unchanged (one line, no output changes), and the flag
matrix exercised the same pipeline 67 times against the pod. Worth
running before branch 2 merges if anything touches the runner again.

## D10. Decisions, resolved

None outstanding. Phase 1 is closed.

1. Extra flags for progress and summary — **rejected.** Both are always
   required, so neither is gated. OBS-01 stays at six flags.
2. `show_all` — **accepted**, and later widened: it is a real field
   settable in every layer, not a command-line convenience. A switch
   that worked in one layer but not another would be a surprise needing
   a footnote, and would need special-casing in each layer to enforce.
   This reversed an earlier decision to keep it out of the file.
3. `run_prompt_set.py` — **left ungated.** Quiet default applies to
   `run_graph.py` only (`ask.py` was deprecated and has been deleted).

**Next action: Phase 2 — UX-01, UX-02, UX-03.** Nothing blocks it.

## D11. `scripts/flag_matrix.sh`

Committed rather than discarded. It runs one prompt under every flag
combination and reports two things: whether any flag changed the answer,
and whether each flag lit only its own component.

Branch 2 adds the file and environment layers *underneath* these same
flags, so this script is how you prove the precedence chain did not
break the CLI behaviour branch 1 established. Re-run it after OBS-02.

Note it takes ~17 minutes and makes 67 LLM calls. Not a suite member —
run it deliberately, when the flag surface changes.

---

## D12. Noted in passing — not Phase 1 work

While verifying progress output, `"Total invoice amount for Lee
Supplies"` paged to exactly 50 pages / 25,000 rows, stopped, and
reported `Synthesized answer: 0 record(s)`. That looks like `MAX_PAGES`
being reached rather than the pod running out of rows — meaning the
aggregate would be computed over a truncated scan, silently. Same
species as the carried-forward "invoice total over a sample" defect.

**Unconfirmed.** Nobody has checked whether the pod actually has more
than 25,000 invoices for that supplier. Recorded so it is not lost, not
because it has been established.

---

## D13. Two things found late, both worth keeping

### `show_all` in a fully-spelled-out file is a no-op

Found by trying a configuration nobody had tested: every key present,
`show_tokens = true` and `show_all = true` together.

`_expand_show_all` only fills flags nobody set explicitly, which is what
makes `--show-all --no-show-planner` mean "everything except the
planner". A file listing all seven keys therefore leaves `show_all`
nothing to fill — it silently does nothing.

**The code is right; the template was wrong.** The first committed
`[tool.spire.diagnostics]` spelled out every key set to `false`, "so the
available flags are discoverable" — and that comment was precisely what
broke it. The template now comments its keys out instead. Two tests pin
the behaviour, because someone reading `_expand_show_all` in isolation
would be tempted to "fix" it.

The existing `test_show_all_from_the_file` passed throughout: it wrote a
file containing *only* `show_all = true`, so it could never have caught
this. A test that exercises the clean case is not a test of the case
people actually write.

### A fragment instead of a whole file cost 11 minutes

Mid-branch, the `[tool.spire.diagnostics]` section was handed over as a
fragment with "replace the section you have". The whole file got
replaced instead, losing `[project]`, `[build-system]`, and
`[tool.pytest.ini_options]`.

The next full suite reported **33 failures in 676 seconds**. None were
real: without `asyncio_mode` the async tests failed wholesale, and
without `addopts` the integration tests ran against services that were
not up.

The tell was `17 deselected` disappearing from the summary line. The
standing rule — always deliver the complete file, never a patch or a
fragment — exists for exactly this, and was not followed.

---
---

# Phase 2 discovery — UX-01, UX-02, UX-03

**Status: discovery done. No design, no code.**

Requirements: UX-01 (structured refusal messages), UX-02 (narrowing
guidance for over-broad queries), UX-03 (truncation disclosure).

## E1. Where the evidence came from

An SME test report (`AR_invoice_Prompt_test.docx`, 2026-07-30) ran 15 AR
prompts and reported "9 passed, 6 failed" — though its own per-prompt
labels list **eight** non-successes, not six. Worth raising with the
tester.

**The report's screenshots are almost certainly not Spire output.** All
five endpoint names in them match no registered Spire tool:

| Report says | Spire has |
|---|---|
| `get_invoice_lines` | `get_receivables_invoice_lines` |
| `get_invoice_line_tax_lines` | `get_receivables_invoice_tax_lines` |
| `list_customer_account_activities` | `get_customer_transactions` |
| `get_account_standard_receipt_applications` | `get_account_receipt_applications` |
| `list_credit_memos` | `list_receivables_credit_memos` |

The format has no `Answer:` header and no `Summary:` block either, and
carries prose ("a strong signature of lockbox batch processing", DSO
commentary) that the synthesizer does not produce. Most likely a chat
client pointed straight at the MCP server, bypassing parser, planner and
synthesizer.

So the report's *outputs* were set aside and its *prompts* were re-run
through `run_graph.py` against the pod: the eight flagged prompts
verbatim, plus four resolved variants supplying the referents the
originals lacked.

**Result: twelve runs, zero errors.** Three answered (exit 0), nine
declined (exit 4). Exit 2, the actual failure code, never appeared.

## E2. The finding that matters most

The loop printed each run's exit code. Reading nine `exit=4` lines in
sequence, the project's own developer — who knows exactly what exit 4
means — reported it as *"too many errors while running"* and *"the
messaging is very very poor"*.

That is the whole of UX-01 in one observation. If the person who wrote
the refusal path reads a screen of refusals as a screen of crashes, an
SME has no chance. The requirements doc argues this from principle; this
is the same conclusion from evidence, and it is the stronger form.

Corollary for the harnesses: **printing a raw exit code next to a
refusal actively causes the misreading.** Worth avoiding in any future
test loop.

## E3. Three distinct defects in the refusal text

All nine refusals came from one of two paths. Eight from the parser's
`capability_message`; one from a planner guard.

### Defect 1 — the message contradicts itself

For *"Get the most recent standard receipts for account 25750"*:

> Spire can look up Address, CreditMemo, CustomerAccount, Invoice,
> PurchaseOrder, ReceivablesInvoice, **StandardReceipt** and Supplier
> [...] This question is about **that kind of record, which Spire
> doesn't track yet.**

`StandardReceipt` is named as supported and then declared untracked, in
the same paragraph. A reader concludes the system is broken, and is
being reasonable.

### Defect 2 — the message misdiagnoses

*"Get tax lines for that invoice line"* refuses with "doesn't track
yet". Spire tracks it perfectly well — the resolved variant *"Get tax
lines for invoice 300000248096352"* answers correctly. The real problem
is the unresolved pronoun.

Same for *"Verify a newly created AR invoice"*: `ReceivablesInvoice` is
supported; what is missing is an identifier, not the capability.

Spire has no conversation memory, so a pronoun cannot resolve. Refusing
is correct. **Saying the wrong reason is not.**

### Defect 3 — the useful sentence is last

Every parser refusal opens with ~90 words listing eight entities and
twenty-one filters, then closes with the one sentence that says what is
actually wrong. Readers skim, hit the wall, and stop before reaching it.

## E4. The template already exists in the codebase

One of the nine refusals reads completely differently. The planner guard
for *"Get the most recent standard receipts"*:

> REFUSED (planner guard): Receipt queries require a customer or a site.
> For example 'receipts for ABC Application Software', or 'receipts at
> Santa Clara'. The top-level receipts collection is too large to list
> unscoped.

Three parts, in the right order: **what is missing**, **two examples to
type**, **why the limit exists**. No entity dump, no filter list.

That is the UX-01 target format, already written, already working, and
already in the repo. Phase 2 is largely a matter of bringing the parser
path up to it rather than inventing anything.

## E5. Three new bugs found by the re-run

Unconfirmed beyond the single observation each, recorded so they are not
lost.

1. **`get_account_receipt_applications` is unreachable from natural
   language.** The tool exists and is registered. Both *"Trace receipt
   applications for this account"* and the resolved *"...for account
   25750"* refuse with "doesn't track yet". Either no KG route exists or
   it does not match this phrasing.
2. **"Show invoice lines for invoice X" answers the wrong question.** It
   returns the invoice header plus `lines: 1` — a count, not the line
   detail asked for. The report's expected result was the line itself.
3. **"Account activity summary for top accounts" silently re-routes.**
   It answered with an exposure ranking of the top 10 of 435 accounts —
   a different question, answered confidently, with no indication the
   question changed. Same species as the carried-forward defects that
   can put a wrong number in front of someone.

## E6. One reported failure that was not a failure

The report flagged *"Get tax lines for that invoice line"* returning
**"0 tax lines found"** as a defect. Spire returns the same result for
the resolved prompt, and the invoice genuinely has no tax lines.

**Correct answer, correctly stated.** Worth telling the tester, along
with the two other flagged prompts — invoice lines and account activity
— which returned answers rather than failing.

The lesson is not that the tester was careless. It is that a correct
answer and a refusal and a crash are currently hard to tell apart, which
is the same problem from a third direction.

## E7. Next action

**UX-01 is done** — see §F below for what was built and what it cost.

**Not yet started:** UX-02 and UX-03. UX-03 connects to two
carried-forward defects (invoice total over a 25-row sample; the 50-page
stop recorded in §D12) and to the SME report's own cash-trends
screenshot, which built a month-over-month trend narrative on a
25-receipt sample and stated it as fact.

One thing UX-03 will find already half-built: `invoices for Lee Supplies`
does disclose its truncation, both in the narration ("25 of 1348") and in
a `Truncation:` block. The carried-forward defect is about TOTALS
computed over the sample, which is a different shape and still open.

---
---

# Phase 2 build — UX-01 (structured refusal messages)

**Status: done, merged.** Branches `phase-2-refusal-messages` and
`phase-2-refusal-tests`.

UX-02 and UX-03 not started.

## F1. Root cause — one bug, three visible faults

`capability.derive_flavor` scanned the model's free-text
`unanswerable_reason` for capitalized words and treated any that was not
an exact KG entity name as an unknown entity. Sentences start with
capitals. Reproduced against the four reasons measured from the pod:

| Detected as an "unknown entity" | Actually |
|---|---|
| `ID` | an abbreviation |
| `To` | the first word of the sentence |
| `Receipt` | a bare noun; `StandardReceipt` is the entity |
| `Filtering` | a gerund |

Four for four. It was also **unstable**: the same prompt flipped from
`unknown_entity` to `unparseable` when the model wrote "The request"
instead of "The question", because `The` is a stopword and `A` is one
letter. Same meaning, different flavor, purely from incidental wording.

That single bug produced both user-visible faults recorded in §E3.
`offending_entity` was never set, so the message fell back to "that kind
of record, which Spire doesn't track yet" — the self-contradiction. And
the model's accurate reason was discarded — the misdiagnosis.

**The model's diagnosis was correct all along.** Three of the four
reasons even named the fix ("I need an identifier such as the
CustomerTransactionId", "can only be retrieved by customer name"). The
work was not to generate better diagnoses; it was to stop throwing the
good ones away.

## F2. What was built

**The prose scan is deleted, not repaired.** `derive_flavor` now trusts
the model, falls back to checking `target_entity` against the KG, then to
UNPARSEABLE. Its docstring says explicitly not to reintroduce a heuristic
over model prose.

**Two new schema fields** (`draft.py`):

| Field | Purpose |
|---|---|
| `unanswerable_kind` | one of five values; the model classifies its own refusal |
| `unanswerable_entity` | the record type, **for wording the reply only** |

The second exists because `target_entity` is REQUIRED to stay empty on a
self-declared refusal — that instruction is the silent-rewrite guard,
stopping the model mangling an out-of-scope prompt into the nearest
supported entity. A separate descriptive field leaves that guard
untouched.

**One new flavor** (`result.py`): `MISSING_IDENTIFIER` — entity and
operation both supported, the prompt simply never says which record.
Previously indistinguishable from "we don't have that record type",
which is what made a supported record read as an unsupported one.

**`UNKNOWN_ENTITY` now splits three ways** in the renderer:

| Case | Message |
|---|---|
| not a KG entity at all | "Contract isn't something I know about" + what I do have |
| KG entity, not a valid query root | "I can look up purchase order lines, but only as part of the record they belong to" + ask for the parent |
| no entity identified | the capability list |

The middle case is new and was a real false statement: `PurchaseOrderLine`
is a KG entity, and the old message denied it.

**The message is three labelled lines**, adapted from the planner guard
that was already the best refusal in the codebase (§E4):

```
Reason:   I can look up receipts, but not by customer account number.
Solution: Scope them by customer or site instead — those I can do.
Example:  receipts for ABC Application Software
```

The ~90-word entity and filter dump survives in exactly one flavor —
genuinely-absent entity — where "here is what does exist" is the answer.

**The renderer prefers structured facts over prose.** Refusals arrive by
two paths with different information quality: self-declared (good model
prose, previously-wrong flavor) and KG validation (correct flavor, raw
dump of 21 filter names). Preferring `offending_filters` /
`offending_entity` when present means the dump never reaches a user and
the model's prose is used only where it is the best thing available.

## F3. A regression caused and undone, worth recording

Adding `unanswerable_kind` included this example in its description:

> 'standard receipts for account 25750' — account number is not a receipt
> filter

Three runs later, that prompt **stopped refusing**. It parsed to
`StandardReceipt` with `customer_name = '25750'`, executed, and returned
zero records. Deterministic, three for three — not model variance.

A refusal had become a silent empty result, which is strictly worse: the
user gets "no receipts found" for a query that was never valid.

The example named a real filter-shaped value, so the model learned a
mapping instead of a refusal. Replaced with one that has nothing to map
onto ("suppliers with more than 50 employees — headcount is not a
supplier filter") plus an explicit prohibition: *do not map an
unsupported value onto a different filter to make the question
answerable*.

**Lesson: an example in a prompt is an instruction.** A field description
teaching the model what NOT to do can teach it what to do instead, if the
counter-example is close enough to something real.

## F4. Verification — as run

Everything below is measured, not argued.

**Full suite: 762 passed, 18 deselected, 1 xfailed.** Up from 672. The
extra deselection is the new integration-marked KG check.

**`05_refusals` 9/9, every message read.** Four defects found this way,
none by inspection: a class name leaked into prose, an internal filter
key leaked, `PurchaseOrderLine` denied, and supplier questions given
receipt examples.

**`08_lifecycle` 31/31, answers unchanged.** Its three refusals also
surfaced two defects — a suggestion that pointed back at the failure, and
a comparison told it needed totals.

**All 18 promised examples answer.** See §F5.

**Two prompts run genuinely in parallel** from separate processes, no
bleed. Analysis of the server agreed: `_persona` is read-only and each
tool opens its own `httpx.AsyncClient`. Caveat on record — two fast
single-step reads is the easy case, not a load test.

## F5. The examples were promises nobody had checked

A refusal's `Example:` line is offered to someone who has just been told
no. If it fails when typed, the refusal has made things worse than
silence.

They were written from what looked plausible and never run. Verifying all
19 against the pod found one failure:

> `open purchase orders for supplier EIP Inc` — **refuses.** Filtering
> POs by supplier name is not supported, which is the very refusal that
> example was offered to resolve.

It appeared in **three** tables. A user following the advice landed
straight back where they started.

Now: `scripts/prompts/10_refusal_examples.txt` holds every promised
example as a runnable set, and a test asserts the tables and the file
cannot drift apart. An example cannot ship without someone having typed
it.

## F6. The entity label table, and its tripwire

Plain nouns beat class names — "AR invoices", not `ReceivablesInvoice`.
This is the one part of the message that does NOT self-update from the
KG, and it was wrong immediately: filled from the **8 target entities**
when a refusal can name any of the **22**. Every related type — tax
lines, invoice lines, buyers, sites, contacts — fell through and printed
its class name.

Found when "tax lines for that invoice line" answered
`I can look up ReceivablesTaxLine, but...`.

Worse, the first fix was wrong too: suppressing unlabelled entities made
the message vaguer for a record Spire genuinely has. `ReceivablesTaxLine`
IS a KG entity — just not a query root. The right fix was the label, not
the suppression.

`tests/test_nl_parser_capability.py` now fails if any KG entity lacks a
label, with an integration-marked twin checking the static list against
the live KG.

## F7. `run_prompt_set.py` — a Phase 1 decision reversed

Phase 1 left the harness ungated, arguing "its output is its purpose"
(§D3, deviation 2). Reading an actual 31-prompt run settled it: the
ANSWERS are the purpose; the Intent/Plan/Outputs blocks are what you
scroll past.

It now takes the same seven flags as `run_graph.py`, with the same file
and environment layers. Its own scaffolding — prompt banners, per-prompt
timing, the roll-up — stays unconditional, because a hundred answers with
no indication which prompt each belongs to would be useless.

Also fixed: `diagnostics.answer()` now flushes. Python block-buffers
stdout when it is a pipe but leaves stderr unbuffered, so every piped run
showed each prompt's diagnostics ABOVE its own answer.

## F8. New bugs found, not fixed

1. **`get_account_receipt_applications` is unreachable from natural
   language.** Tool exists, registered, both phrasings refuse. Confirmed
   again this session — "Trace receipt applications for account 25750"
   now routes to `CustomerAccount` instead.
2. **"Show invoice lines for invoice X" answers the wrong question** —
   returns the header plus `lines: 1`, a count, not the line detail.
3. **"Account activity summary for top accounts" silently re-routes** to
   an exposure ranking of the top 10 of 435 accounts.
4. **Two `Answer:` headers on column queries** —
   `_format_synthesized(summary_only=True)` and
   `_format_projected_table` each emit one. Pre-existing, in
   `display_formatters.py`.

## F9. What it cost, honestly

The design was "one new field". It took four fields across three files,
plus a regression caused and undone, plus a wrong first fix to the label
table, plus a guard that tested the wrong predicate and had to be
corrected.

**Every one of those was found by running something and reading the
output. None was found by reading code.** The prose scan, the mapping
regression, the 14 missing labels, the guard testing `is_known_entity`
instead of `target_entities`, the broken example in three tables — five
defects, five discovered by measurement.

That is the same pattern as the rest of this project's history, and it is
the argument for the tripwires added alongside the fix rather than after
it.

---

# Phase 2A discovery — COL-01, COL-02, COL-03, CSV-01

**Opened 2026-07-31. P0, ahead of the remainder of Phase 2. Nothing built
yet — this section is discovery only.**

Requirements added to `spire_enhancement_requirements.md` v1.1 §4A.

## G1. How it was raised

Not from the requirements list. The SME reported that naming columns in a
prompt did not return those columns, and — the important part — that
adjusting the prompt wording made it work. The complaint was explicitly
about the *shape* of the fix, not the individual prompts:

> *"I don't want to fix by adjusting the prompt the way that you are
> expecting... How many times do I need to fix? I need a broader solution."*

That is the correct instinct, and it is why this is a requirement rather
than five bug fixes.

## G2. The measurement

Five prompts, run with `--show-parser --show-raw-output`, output in
`t_fields.txt`. Not inspection — every finding below came from reading
output.

| # | Term | Parsed as | Outcome |
|---|---|---|---|
| 1 | `item details` | no `fields` at all | Data **was fetched** — `Description: 'Printer M32240'` present in raw output. Display printed `lines: 1` |
| 2 | `'created by'` | an **entity** to include | Refused: "not a supported entity" |
| 3 | `supplier-site` | `include: ['Address']` | **Wrong child returned, silently.** 25 addresses presented as sites |
| 4 | `'business unit'` | an entity to include | Refused correctly. Control case — the mechanism works |
| 5 | `who columns` | dropped from `fields` | **Silently discarded.** Clean 25-row table, no indication anything was lost |

Five prompts, four distinct root causes. Only one is synonym matching.

## G3. Three findings

### Finding 1 — the resolver already exists, for everything except fields

`kg_vocabulary`, 97 rows, eight `vocab_kind` values:

```
country                          entity_synonym
po_status                        relationship_phrase
supplier_classification          supplier_site_bu
supplier_status                  supplier_business_relationship
```

`vendor`→`Supplier`. `agent`→`Buyer`. `draft`→`INCOMPLETE`. Deterministic,
KG-authored, no LLM call, no similarity search. Exactly the mechanism the
SME asked for.

**There is no `field_synonym`.** Fields are the one dimension for which
nobody authored one. The fix is a ninth `vocab_kind` in an existing table
— not a new subsystem.

### Finding 2 — synonyms alone would have fixed none of the five

The target fields do not exist.

- `Supplier` has **four** field rows: `Supplier`, `Status`, `SupplierId`,
  `SupplierNumber`.
- `CreatedBy` appears **nowhere** in all 194 rows of `kg_entity_field`.
- `CreationDate` exists only in `kg_entity_filter` — filterable, never
  projectable.
- `Site` is a registered entity in `kg_entity` with **zero** rows in
  `kg_entity_field`. That is why `supplier-site` had nothing to land on
  and fell through to `Address`.

**Coverage precedes mapping.** COL-01 before COL-02. Reversing that order
maps terms onto fields that cannot be projected — which looks like
progress and delivers em dashes.

### Finding 3 — the silent drop is the safety defect

Prompts 3 and 5 both returned confident, well-formed, correctly-formatted
tables. Neither is distinguishable from success by reading the output.
Prompt 3 is worse than a refusal: it answered with the wrong data.

This is why COL-03 is built **first** despite being the smallest. Until
misses are visible, no resolver's hit rate can be measured — we would be
shipping COL-02 with an unknown miss rate and no way to find out.

## G4. Why not an LLM call, and why not a vector store

Both were raised and both were rejected. Recording the reasoning so it is
not relitigated.

**A second LLM call** — rejected on latency, and unnecessary. The parse
call *already performs this mapping correctly when the vocabulary is
present*: in the same run, `supplier name and status` resolved cleanly to
`fields: ['Supplier', 'Status']`. The mapping capability is not missing.
The vocabulary is. Widening the menu that call already receives costs input
tokens, not a round-trip.

**A vector store / embedding similarity** — rejected on accuracy, which is
the opposite of the usual expectation. Prompt 3 *is* what nearest-neighbour
matching looks like when it goes wrong: `supplier-site` → `Address` is
semantically close, factually wrong, and silently confident. Embeddings
would make that failure class more common and considerably harder to
debug. Additionally the field vocabulary is bounded at 194 rows — a lookup
problem, not a search problem. Vector search earns its cost over unbounded
corpora.

**Third-order point:** a deterministic KG lookup keeps Design 3 intact.
Field resolution becomes a KG lookup exactly as tool selection is. Two LLM
boundaries, unchanged.

## G5. The channel bug

Distinct from coverage and from synonyms, and easy to miss.

The word **"include" is doing routing work it should not do.** The user
means "also show this column". The parser reads it as "join this child
entity". That is why `include 'created by'` — a request for a *field* —
was refused as an unsupported *entity*.

A perfect synonym table does not fix prompt 2, because the term never
reaches the field channel at all.

Resolution must be decided by **what the term resolves to**, not by the
preposition that introduced it. Note `address` is legitimately both a child
entity and a flattened column, so the same word must resolve two ways
depending on intent — the channel cannot be decided lexically.

## G6. CSV export (CSV-01) — the trap in the request

The request as stated: *"if the output says 400 records but only 25 are
displayed, the CSV should contain all 400."*

**Spire does not have the 400.** The run states it plainly:
`suppliers: 426 total in source; 25 examined for filtering`. Twenty-five
rows were fetched; 401 were never retrieved. There is nothing in memory to
write.

So CSV export is not a formatting feature. It is a **data-acquisition**
feature, and the full-set version is what makes `06_slow.txt` take minutes.

Resolved (SME, 2026-07-31): **default to exporting what was fetched, with
a partial marker in the file; offer opt-in full pagination.** The marker is
non-negotiable.

The reason it is non-negotiable, recorded: a truncated CSV is worse than a
truncated screen. A file is saved, mailed and cited long after the "25 of
426" note has scrolled away. Shipping CSV before UX-03 (truncation
disclosure) would industrialise the wrong-number problem rather than fix
it. Hence CSV-01 depends on UX-03.

**Granularity, resolved:** one file per output *step*, not per prompt.
Prompt 1 produced two result sets (`po` and `purchaseorderline`). A
prompt-level file would have to discard one or flatten both.

**The summary question, resolved:** a run writes a directory with a
`manifest.csv` recording per step — prompt, step name, rows written, rows
available, truncated y/n, exit code. Side benefit: this finally gives
`run_prompt_set.py` a scoreable artifact. "The tally is not a verdict" has
had nothing better to offer in its place until now.

## G7. Open questions

1. **The prompt 1 narration cites data not in the raw output.** The answer
   states quantity 2, category "Printers", and 758.00 — none of which
   appear in the row `--show-raw-output` printed. Either that diagnostic
   abbreviates, or the synthesizer is inventing. **Different fixes.** Not
   yet determined which.
2. **Prompt 1 is also the known "invoice lines returns a count" defect** —
   `lines: 1` where line detail was asked for. Same shape, already carried
   forward. May be one fix, not two.
3. **Ambiguity across entities is unresolved.** `status` exists on nine
   entities; `Ordered` and `Total` collide across PurchaseOrder,
   PurchaseOrderLine and PODistribution; `receipt` means goods-received in
   P2P and cash-received in AR. A synonym that resolves differently by root
   entity needs a row per entity, not one global row. No design yet.
4. **Menu growth is measurable and must be measured.** Unlike the schema
   growth recorded in the Phase 2 numbers — which Gemini does not count in
   `input_tokens` — vocabulary added to the KG menu *will* show in
   `input_tokens`. The parse-token baseline is usable for this change,
   unlike for `draft.py`.
5. **Why does `who columns` alone drop silently?** Eleven prompts, ten
   refuse loudly, one vanishes. Plurality and jargon-as-a-collective were
   both tested and excluded — see §G9. No explanation. Do not design
   around it; find out.

## G8. Next action

Build order is COL-03, COL-01, COL-02, CSV-01 — disclosure first, then
coverage, then synonyms, then export.

Not yet done, and needed before any code:

- A labelled prompt set for column requests, indexed against the real 194
  fields rather than invented names. Should cover: valid single and
  multiple columns, jargon terms, near-miss wording, cross-entity terms
  (must refuse), and the multi-field expansions.
- Curl verification of WHO columns on the pod before authoring any
  `kg_entity_field` row. Standing rule: curl before code.

---

## G9. Second measurement round — the first reading was wrong

**2026-07-31, same day, eleven further prompts.** This section corrects
§G3 Finding 3 and the first draft of COL-03. Recorded in full because the
error is instructive and because the requirement was already written when
it was found.

### What was believed after round one

Five prompts, two of which silently dropped a term. COL-03 was specced
around silent dropping: *never discard a requested column without saying
so.* The stated rationale was that silent failure is the dangerous case
because it cannot be distinguished from success.

### What eleven prompts actually show

| Behaviour | Count | Terms |
|---|---|---|
| **Wholesale refusal** | 5 | `quantum flux`, `quantum fluxes`, `flurbles`, `audit columns`, `created by` |
| **Silent drop** | 1 | `who columns` |

Silent dropping is the **rare** case. The dominant failure is a total
refusal that discards the whole query — including columns that resolved
perfectly well.

```
List active suppliers with supplier name and created by
  → Reason: I can look up suppliers, but not the way this question narrows them.
  → no rows at all
```

`supplier name` is valid. It resolved in every other prompt in the round.
It was thrown away because `created by` was not recognised. **A user who
names five columns and mistypes one gets zero rows.**

### Hypotheses tested and excluded

Two explanations for why `who columns` alone vanished were proposed and
both were measured, not argued:

- **Plurality** — excluded. `quantum fluxes` refuses.
- **Jargon-as-a-collective** — excluded. `audit columns` refuses, and does
  so while explicitly acknowledging it is not "a specific field".

The mechanism remains **unexplained**. A plausible reading is that "who"
does not register as a field noun at all, but that is one data point and
an untested explanation. Recorded as open question §G7.5 rather than
designed around.

### The finding that was hiding under the wrong one

Where the refusal fires, **the accurate diagnosis already exists and is
thrown away.** Every loud refusal carried a correct, specific reason on
the diagnostic line and showed the user generic filter advice instead:

```
user sees:   I can look up suppliers, but not the way this question narrows them.
             Solution: Narrow by country, status or name instead.
diagnostic:  The 'created by' field is not available for suppliers.
```

Three more, all discarded:

- `The requested "audit columns" are not available as a specific field.`
- `The field 'quantum flux' is not supported for the Supplier entity.`
- `The requested field 'flurbles' is not supported.`

**This is the UX-01 root cause, in a second place.** The Phase 2 finding
was "the model's diagnosis was correct all along" — the prose scan
discarded it. Here the presentation layer discards it again, for a
different reason, in a different code path. Worth checking whether there
is a third.

### Also confirmed

- **Wrong flavor.** Column requests refuse as `unsupported_filter`, with a
  Solution line offering "narrow by country, status or name" — filter
  advice for a column problem.
- **The channel bug reproduces cleanly.** Same term, `with` vs `include`:
  `quantum flux` gives `unsupported_filter` under "with" and "entity is
  not supported" under "include". The preposition alone changes the
  refusal category.
- **Normalization already works.** `supplier_name` → `Supplier`,
  `supplier_number` → `SupplierNumber`, unaided. Group B of the prompt
  set is largely redundant. Consistent with §G4: the mapping capability is
  present, the vocabulary is not.
- **The narration defect reproduces a third time.** Two runs cited
  "Taxpayer Country Code", which is not among Supplier's four fields and
  was not in the displayed columns.

### What changed in the requirements

COL-03 rewritten and renamed — *Unresolved column disclosure* became
*Partial column resolution and disclosure*. Partial resolution is now the
primary clause; disclosure is secondary; two further clauses added for
using the existing diagnosis and correcting the flavor.

COL-03 is **larger** than first specced, not smaller.

### The process note

The assessment moved twice in one session: silent-drop-is-the-danger, then
detection-already-exists-so-this-is-just-plumbing, then the above. The
second was an overcorrection off a single observation — one prompt showing
a discarded diagnostic was read as characterising all cases.

The rule that held: each reversal came from running more prompts, and each
was cheap. Eleven prompts across three rounds, perhaps four minutes of pod
time, caught a requirement that was written around the rare case.

**The specific trap:** round one's five prompts were chosen to cover
*categories* of vocabulary, not to vary one thing at a time. The
disambiguation rounds — which held the entity constant and varied only
plurality, or only the preposition — were what produced usable findings.
Coverage first, then controlled variation.
