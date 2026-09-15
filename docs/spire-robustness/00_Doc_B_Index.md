# SPIRE — Doc B Index

**Companion to:** `SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md` (Doc A), in this folder.
**Document version:** 1.0
**Created:** 2026-09-14
**Last revised:** 2026-09-15

**What this file is.** The index to SPIRE's forensic record. It carries
the status snapshot and the registers — the two things that change at
every checkpoint — plus the session entry template and the pointer
lists to the per-phase detail files.

**What this file is not.** It does not carry session entries or feature
designs. Those live in the per-phase files in this folder:

| File | Holds |
|---|---|
| `00_Doc_B_Index.md` | This file. Snapshot, registers, taxonomy, template, pointers, dev/runtime, working-style. |
| `01_Phase_01_Audit_and_Baseline.md` | Session entries for Phase 1 (S002, S003, …). |
| `04_Phase_04_Structure.md` | Session entries for Phase 4 (S001) and the Phase 4d UI/API design. |
| `NN_Phase_NN_*.md` | Created as each phase begins. |

**Why the split.** A single growing file costs the same to regenerate
whether or not its content has changed. Splitting living content (this
index) from frozen content (per-phase session and design detail) means
each checkpoint regenerates only what actually moved. The index stays
under ~15KB; each phase file is written once and appended to, then
frozen when its phase ends.

---

## 0. How to use this file

1. **Append, never overwrite.** Corrections are new entries that
   reference old IDs.
2. **Newest session at the top of each phase file.** Registers in §2
   here are updated in place — indices, not history.
3. **Assign IDs once.** Session `S###`, bug `B-###`, investigation
   `INV-###`, decision `D-###`, question `Q-###`. Never reuse.
4. **Every claim has a command and an output.** If you cannot paste the
   command and its output, it is not evidence.
5. **Cross-reference Doc A.** Every work item names the phase and
   section it belongs to.
6. **Checkpoint discipline.** At every checkpoint:
   1. Update §1 (snapshot) and §2 (registers) in this file.
   2. Prepend the full session entry to the current phase file.
   3. Add a one-line pointer to §4 of this file.
   4. Add a line to §5 for any new or changed design.

### ID schemes

| Type | Format | Example | Meaning |
|---|---|---|---|
| Session | `S###` | `S001` | A work session in one window |
| Bug | `B-###` | `B-007` | A defect found during a session |
| Investigation | `INV-###` | `INV-003` | A diagnostic that did not (yet) produce a bug fix |
| Decision | `D-###` | `D-012` | A session-level decision not yet in Doc A's Appendix C |
| Question | `Q-###` | `Q-004` | An open question carried across sessions |
| Work item | `WI-S###-NN` | `WI-S001-03` | A single unit of work inside a session |

### Growth

This index stays small by design. If it exceeds ~15KB, something that
belongs in a phase file has leaked back into it. Move it out.

Phase files are append-only within their phase. When a phase ends, its
file is frozen and a new file is created for the next phase. Nothing is
deleted.

---

## 1. Current status snapshot

*Update at every checkpoint. Keep to one screen.*

```
Date:                2026-09-15
Last session:        S002 (in progress)
Current phase:       Phase 1 — Audit & Baseline
Integration branch:  hardening-master
Current branch:      phase-1
master:              frozen at 14dce82 (PR #145, phase-4d-ui-api)
Last commit on
hardening-master:    c57cf67 (PR #147, tooling-dev-ports)
Working tree:        clean (dev tree at ~/pocs/spire)
Runtime tree:        ~/pocs/spire-runtime — running 3333/8000/8888, ngrok-exposed
pytest -q:           1008 passed / 22 deselected (integration — deferred per D-002)
Prompt suite:        — (baseline capture is task 1.10)
KG version:          — (to be established in Phase 3g)
Open bugs:           0
Open investigations: 0
Open questions:      2 (Q-001, Q-002)
Next action:         WI-S002-03 — task 1.3 (move PDFs and XLSX out of source tree)
```

---

## 2. Registers

*Indices, not history. Updated in place at every checkpoint.*

### 2.1 Bug register

| ID | Phase | Section | Title | Severity | State | First seen | Closed |
|---|---|---|---|---|---|---|---|
| *(none yet)* | | | | | | | |

**Severity values:** wrong-data · crash · missing-capability · cosmetic
**State values:** open · investigating · fixed-pending-test · fixed · deferred · closed-as-evidence

### 2.2 Investigation register

| ID | Phase | Title | Outcome | Session |
|---|---|---|---|---|
| *(none yet)* | | | | |

**Outcome values:** no-defect · defect-found (→ bug ID) · inconclusive · abandoned

### 2.3 Session-level decision register

*Decisions made during a session that are not yet in Doc A's Appendix C.
Promote to Doc A when stable.*

| ID | Date | Session | Decision | Rationale | Proposed for Doc A? |
|---|---|---|---|---|---|
| D-001 | 2026-09-15 | S002 | `hardening-master` is the integration branch for the entire v3.2 plan. Every phase sub-branch spawns off it and merges back via PR. `hardening-master` merges to `master` once, when the plan completes. `master` stays frozen at the fork point until then. | Keeps `master` as the eventual shippable target and `hardening-master` as the accumulation point. The runtime clone pulls from `hardening-master`, so testers see only merged sub-phases. | No — working-style decision. |
| D-002 | 2026-09-15 | S002 | Integration tests (the 22 marked `integration` in `pyproject.toml`) are deferred. Not run, not investigated, not fixed during Phase 1. | Deferred per user instruction. Note: `tests/test_kg_metadata.py` touches Oracle but is not marked `integration` — a Phase 1 finding. | No — working-style decision. |
| D-003 | 2026-09-15 | S002 | Doc B is split into this index plus one file per phase under `docs/spire-robustness/`. Session entries and designs live in the per-phase files; the index carries snapshot, registers, and pointer lists only. | Every checkpoint was regenerating a single growing file, most of it inert. Splitting living content from frozen content makes each checkpoint cheap and each file independently maintainable. | No — a Doc B structural decision. Doc A unaffected. |

### 2.4 Open questions register

| ID | Raised | Session | Question | Owner | State |
|---|---|---|---|---|---|
| Q-001 | 2026-09-15 | S001 | API port for the runtime — `8000` default; runtime uses 3333/8000/8888; dev uses 4444/9000/9999 via `.spire-dev.env`. Confirm no further change needed. | Bhagavan | open |
| Q-002 | 2026-09-15 | S001 | Tester's browser — same machine or same network? Runtime binds `0.0.0.0`, no auth. | Bhagavan | open |

**State values:** open · resolved (→ decision ID) · abandoned

---

## 3. Test taxonomy (reference)

| Test kind | When used | Evidence required |
|---|---|---|
| Deterministic | Bug fires every time | Single-run pass/fail |
| Probabilistic | Bug fires some fraction of the time | N ≥ 20 runs; distribution |
| Byte-equality | Behaviour must not change | `diff` against golden file |
| Per-quirk | Endpoint quirk must be honoured | One test per quirk kind |
| KG integrity | KG rows and counts must match | `spire-ops kg` output |
| Timing | Latency change claimed | `time` output; mean/median/p95 |
| Load | Concurrency claimed | Concurrency N; failures; latency |
| Corpus validation | Prompt suite coverage | `--validate` pass count |
| Prompt suite | End-to-end answers | Pass count on all sets |
| Manual probe | Exploratory, not automated | Command + raw output |
| Unit | Isolated function behaviour | `pytest tests/unit/...` |
| Integration | Cross-module with external services | `pytest tests/integration/...` |

---

## 4. Session pointers and template

*One line per session. Full entry in the file named. Newest at top.*

| Session | Date | Phase | Branch | Summary | File |
|---|---|---|---|---|---|
| S002 | 2026-09-15 | 1 | `phase-1` | Phase 1 opens: task 1.2 (display_formatters move) + dev/runtime port separation. In progress. | `01_Phase_01_Audit_and_Baseline.md` |
| S001 | 2026-09-15 | 4 | `phase-4d-ui-api` | Phase 4d: FastAPI backend + Streamlit UI built, verified, merged to `master` (PR #145). Complete. | `04_Phase_04_Structure.md` |

### 4.0 Session entry template

The full template lives in `TEMPLATE_Session_Entry.md` in this folder. Do
not duplicate it here — one copy, one place to keep current.

When starting a new session, copy the template block from that file and
fill it in; the filled entry goes into the current phase file, not here.

---

## 5. Design pointers

*One line per design. Full design in the phase file named.*

| Design | Phase | Opened in | Status | File |
|---|---|---|---|---|
| Phase 4d — UI and API layer | 4 | S001 | complete | `04_Phase_04_Structure.md` |

---

## 6. Dev / runtime separation

**Why this exists.** The tester runtime clone at `~/pocs/spire-runtime`
must keep running undisturbed while development continues in
`~/pocs/spire`. Two instances at once means two sets of ports.

**Topology.**

| Instance | Path | Branch | Ports (MCP/API/UI) | Tunnel |
|---|---|---|---|---|
| Runtime | `~/pocs/spire-runtime` | `hardening-master` | 3333 / 8000 / 8888 | ngrok → 8888 |
| Dev | `~/pocs/spire` | feature branches | 4444 / 9000 / 9999 | none |

**Mechanism.** `.spire-dev.env` (gitignored) exists only in the dev tree.
`run-all.sh` sources it if present; otherwise uses runtime defaults. No
flag, no remembering.

**Runtime untouched.** The runtime clone never sees `.spire-dev.env`
because the file is gitignored, so it always runs on the default ports.

**Runtime updates (deliberate, rare).** Change to the runtime clone and
run:

- `git fetch origin hardening-master`
- `git reset --hard origin/hardening-master`
- `pip install -e .` in the runtime venv
- `./run-all.sh`

No promotion script exists. Promotion is a manual, deliberate action.

---

## 7. Working-style decisions (informal index)

- **D-001** — `hardening-master` is the integration branch.
- **D-002** — Integration tests deferred during Phase 1.
- **D-003** — Doc B split: index + one file per phase.
- **PR-based merges always.** No local `git merge` into long-lived branches.
- **Branch-first for code, tooling, and non-README docs.** README and pure doc updates may go direct.
- **`personas.yaml` untrack (task 1.1) deferred** per user instruction.
- **One command at a time in interactive sessions.** Run, confirm output, then next.

---

*End of index. Phase detail in `NN_Phase_NN_*.md` in this folder.*