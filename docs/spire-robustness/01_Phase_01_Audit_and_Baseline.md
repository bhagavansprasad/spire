# SPIRE — Phase 1 — Audit and Baseline

**Session log for Phase 1** (Doc A §7).
**Index:** `00_Doc_B_Index.md` in this folder.
**Newest session at the top.** Append-only within the phase. When Phase 1
ends, this file is frozen and `02_Phase_02_Correctness.md` opens.

---

### S002 — 2026-09-15 — Phase 1 opens: hygiene + dev/runtime separation

**Phase:** Phase 1 — Audit & Baseline (Doc A §7)
**Branch:** `phase-1` (fresh, off `hardening-master`)
**Session goal:** Begin Phase 1. Complete the mechanical hygiene tasks
(1.2–1.4) and set up the dev/runtime separation so ongoing development
can proceed without disturbing the tester runtime.
**Outcome:** in progress — 1.2 done; 1.3 and 1.4 pending; dev/runtime
separation done

**Inputs received this session:**
- `graph_kg` context bundle (from S001) — pipeline shape, executor
  contract, KG schema.
- `synthesizer` context bundle (from S001) — response models,
  truncation narration, local-summary rules.
- User's working-style decisions: `hardening-master` as integration
  branch; integration tests deferred; `personas.yaml` untrack deferred.

**Outputs:**
- Task 1.2 complete (display_formatters move, PR #146).
- Dev/runtime port separation complete (PR #147).
- Doc A §7.7 deviation note pending.
- Doc B split into index + per-phase files.

---

#### Work items

##### WI-S002-01 — Task 1.2: move `display_formatters.py` to `src/spire/rendering/`

| Field | Value |
|---|---|
| Type | refactor |
| Test kind(s) | unit |
| Doc A reference | §7.3.2, §7.4 (task 1.2) |
| Bug ID | — |
| Investigation ID | — |
| State | verified |

**Objective.** Move `scripts/display_formatters.py` (1440 lines,
presentation-only) out of `scripts/` and into the package at
`src/spire/rendering/formatters.py`, so an installable entry point can
reach it without a sys.path trick. Add a re-export `__init__.py`.

**Recon findings.** Doc A §7.3.2 said "Update four imports." Actual
count: **8 import statements across 6 files, 1 hard path reference,
plus 2 docstring/comment edits.**

Importers (all updated):

- `scripts/promptkit.py` — 2 imports (line 392, line 482; both inside
  functions and indented)
- `scripts/run_prompt_set.py` — 1 import (line 86)
- `scripts/run_graph.py` — 1 import (line 49)
- `scripts/verify_bug1_step3.py` — 1 import + 1 hard path
  (`DISPLAY_PY = REPO_ROOT / "scripts" / "display_formatters.py"`, line 37)
- `tests/test_display_summary_only.py` — 2 imports (lines 25, 160)
- `tests/test_bug1_step3_supplier_details.py` — 1 import (line 39)

**Investigation — an early `sed` missed the indented imports.**

The first pass used `sed -i 's|^from display_formatters import |...|'`
with an anchored pattern. That works for top-of-file imports but misses
the two imports inside functions in `promptkit.py` and the one inside a
function in `verify_bug1_step3.py`. Tests passed anyway (1008) because
nothing exercised those code paths. The failure mode was latent: the
moment `promptkit.py`'s diagnostic helper ran, it would have raised
`ModuleNotFoundError: No module named 'display_formatters'`.

Fixed by re-running `sed` without the `^` anchor and with the `g` flag
on the affected files.

**Commands.**

- `mkdir -p src/spire/rendering`
- `git mv scripts/display_formatters.py src/spire/rendering/formatters.py`
- `sed -i 's|from display_formatters import|from spire.rendering.formatters import|g' scripts/promptkit.py`
- `sed -i 's|from scripts\.display_formatters import|from spire.rendering.formatters import|g' scripts/verify_bug1_step3.py`
- `sed -i 's|^from spire\.rendering import |from spire.rendering.formatters import |g' scripts/run_prompt_set.py scripts/run_graph.py tests/test_display_summary_only.py tests/test_bug1_step3_supplier_details.py`
- `sed -i 's|REPO_ROOT / "scripts" / "display_formatters.py"|REPO_ROOT / "src" / "spire" / "rendering" / "formatters.py"|' scripts/verify_bug1_step3.py`

**Verification — no stale references in code.**

```
$ grep -rn "display_formatters" --include="*.py" --include="*.sh" . | grep -v "\.git/" | grep -v "context_out/"
./src/spire/rendering/__init__.py:3:`formatters.py` lived at `scripts/display_formatters.py` until Phase 1
```

The remaining hit is a deliberate historical note in the `__init__.py`
docstring.

**Verification — tests.**

```
$ python -m pytest -q tests/test_display_summary_only.py tests/test_bug1_step3_supplier_details.py
28 passed in 0.35s

$ python -m pytest -q
1008 passed, 22 deselected in 191.10s (0:03:11)

$ python -m pytest -q -n auto --dist loadfile
1008 passed in 51.25s
```

Parallel test run via `pytest-xdist` added to `requirements-dev.txt`
this session. `-n auto` uses one worker per CPU; same collection
(1008/1030, 22 deselected), all pass.

**Files touched.**
- `scripts/display_formatters.py` → `src/spire/rendering/formatters.py`
  (rename, 100% match)
- `src/spire/rendering/__init__.py` (new)
- `scripts/promptkit.py`, `scripts/run_prompt_set.py`,
  `scripts/run_graph.py`, `scripts/verify_bug1_step3.py`
- `tests/test_display_summary_only.py`,
  `tests/test_bug1_step3_supplier_details.py`
- `src/spire/synthesizer/synthesizer.py` (docstring comment)
- `requirements-dev.txt` (added `pytest-xdist`)

**Commits.**
- `7ce0eff` — phase 1.2: move display_formatters to
  src/spire/rendering/
- PR #146 — merged to `hardening-master`

**Cross-references.**
- Doc A §7.3.2 (the task), §7.7 (deviation: "four imports" → 8 import
  sites + 1 hard path + 2 docstring edits)
- Follow-up: tasks 1.3, 1.4 on `phase-1`

---

##### WI-S002-02 — Dev/runtime port separation

| Field | Value |
|---|---|
| Type | tooling |
| Test kind(s) | manual probe |
| Doc A reference | none — out of plan scope |
| Bug ID | — |
| Investigation ID | — |
| State | verified |

**Objective.** Allow the local dev instance and the tester runtime to
run at the same time without port collision.

**Investigation — three designs considered, then rejected.**

1. **A `deploy-runtime.sh` promotion script.** Rejected: too heavy, ran
   on every save, changed what testers saw without a deliberate
   decision.
2. **`SPIRE_DEV=1` environment flag.** Rejected: forgetting the flag
   silently points dev at runtime ports.
3. **File presence.** `.spire-dev.env` in the repo root. If the file
   exists, `run-all.sh` sources it. Dev tree has the file; runtime tree
   does not. **Chosen.**

**Design.**

- `.spire-dev.env` (gitignored) in the dev tree: `SPIRE_MCP_PORT=4444`,
  `SPIRE_API_PORT=9000`, `SPIRE_UI_PORT=9999`.
- `run-all.sh` sources it if present; otherwise 3333/8000/8888.
- `run-server.sh` reads `SPIRE_MCP_PORT` from env, default 3333.
- `run-all.sh` passes `SPIRE_MCP_URL` and `SPIRE_API_URL` down to
  children.
- `.gitignore` includes `.spire-dev.env`.

**Verification.**

```
$ ./run-all.sh
Log directory: logs
Ports:  MCP 4444   API 9000   UI 9999
MCP   pid=239687   http://127.0.0.1:4444     log: logs/mcp.log
API   pid=239702   http://localhost:9000     log: logs/api.log
UI    pid=239722   http://localhost:9999     log: logs/ui.log
```

No port-collision warnings. Dev instance runs alongside the runtime.

**Files touched.**
- `run-all.sh`, `run-server.sh`, `.gitignore`, `.spire-dev.env` (local)

**Commits.**
- PR #147 — `tooling: dev port overrides via .spire-dev.env` — merged
  to `hardening-master`

---

##### WI-S002-03 — Task 1.3: move PDFs and XLSX out of source tree

| Field | Value |
|---|---|
| Type | refactor |
| Test kind(s) | unit |
| Doc A reference | §7.3.2, §7.4 (task 1.3) |
| Bug ID | — |
| Investigation ID | — |
| State | open |

**Objective.** Move `docs/*.pdf` and `tests/*.pdf` to `docs/pdf/`, and
`docs/spire_tools_modules.xlsx` to `docs/data/`. Doc A §7.3.2.

**Commands and output.** *(to be filled)*

**Files touched.** *(to be filled)*

**Commits.** *(to be filled)*

**Cross-references.**
- Doc A §7.3.2
- Follow-up: task 1.4

---

##### WI-S002-04 — Task 1.4: remove scratch files from repo

| Field | Value |
|---|---|
| Type | refactor |
| Test kind(s) | unit |
| Doc A reference | §7.3.2, §7.4 (task 1.4) |
| Bug ID | — |
| Investigation ID | — |
| State | open |

**Objective.** Remove `source-tree.txt` and `isolation/` from the repo.
Add both to `.gitignore`. Doc A §7.3.2.

**Commands and output.** *(to be filled)*

**Files touched.** *(to be filled)*

**Commits.** *(to be filled)*

**Cross-references.**
- Doc A §7.3.2
- Follow-up: task 1.5 (registry drift map) — first audit task

---

#### Phase 1 remaining work

| # | Task | State |
|---|---|---|
| 1.1 | Untrack `personas.yaml` | **Deferred** per instruction |
| 1.2 | Move `display_formatters.py` | done (WI-S002-01) |
| 1.3 | Move PDFs and XLSX out of source tree | WI-S002-03 |
| 1.4 | Remove scratch files | WI-S002-04 |
| 1.5 | Registry drift map | not started |
| 1.6 | Bug inventory | not started |
| 1.7 | Dead code inventory | not started |
| 1.8 | Inconsistency inventory | not started |
| 1.9 | In-flight work inventory | not started |
| 1.10 | Baseline metrics | not started |
| 1.11 | Three golden outputs | done (S001) |
| 1.12 | Probabilistic-behaviour map | not started |

#### Observations carried forward

- **Double `classify` call per prompt** — observed in all three golden
  outputs (S001) and via the API. Real double LLM call or duplicated
  log line? Unresolved. Belongs in §H (probabilistic-behaviour map) and
  §B (bug inventory).
- **Supplier count drift** — 431 → 433 → 434 across runs, and open-PO
  count 44 / 67 on identical prompts. Two hypotheses: (a) pod changing
  between runs, (b) `search_suppliers` sampling a non-deterministic
  page of 25. Belongs in §H.
- **`tests/test_kg_metadata.py`** touches real Oracle but is not marked
  `integration`. Marker-application inconsistency — belongs in §D
  (inconsistency inventory) and §B (bug inventory).
- **Doc A §7.3.2 "Update four imports"** was undercounted. Actual: 8
  import sites + 1 hard path + 2 docstring edits. Belongs in §A
  (registry drift map) as an example of the same "information appears
  in more than one place" failure class the audit exists to enumerate.

#### Blockers / open questions

- Q-001: API port for the runtime — see index §2.4.
- Q-002: Tester's browser — see index §2.4.

#### Next session should

- Open a fresh window with Doc A + `00_Doc_B_Index.md` + this file.
- Start at **task 1.3** (WI-S002-03) on branch `phase-1`.
- Complete 1.3 and 1.4 (quick), then begin 1.5 (registry drift map).

#### Commits on branch `phase-1`

*(none yet — 1.2 was on `phase-1-hygiene`, merged to `hardening-master`
via PR #146)*