# SPIRE — Status and Evidence Log

**Companion to:** `SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md` (Doc A)
**Document version:** 1.0
**Created:** 2026-09-14
**Last revised:** 2026-09-14

**What this file is.** Doc A is the frozen plan. This file is the append-only forensic record of implementing it. Every session, every bug, every investigation, every test, every command, and every result lives here. Nothing is deleted. Newest session at the top.

**What this file is not.** This file does not change the plan. If the plan needs to change, record it as a session-level decision in §2.3 and, if it warrants a permanent change, propose a Doc A amendment at the next checkpoint.

---

## 0. How to use this file

1. **Append, never overwrite.** Corrections are new entries that reference old IDs.
2. **Newest session at the top of §4.** The registers in §2 are updated in place — they are indices, not history.
3. **Assign IDs once.** Session `S###`, bug `B-###`, investigation `INV-###`, decision `D-###`, question `Q-###`. Never reuse.
4. **Every claim has a command and an output.** If you cannot paste the command and its output, it is not evidence.
5. **Cross-reference Doc A.** Every work item names the phase and section it belongs to.
6. **Checkpoint discipline.** At every checkpoint, update §1 (snapshot) and §2 (registers), then add the full session entry to §4, then emit the checkpoint block for the next window.

### ID schemes

| Type | Format | Example | Meaning |
|---|---|---|---|
| Session | `S###` | `S001` | A work session in one window |
| Bug | `B-###` | `B-007` | A defect found during a session |
| Investigation | `INV-###` | `INV-003` | A diagnostic that did not (yet) produce a bug fix |
| Decision | `D-###` | `D-012` | A session-level decision not yet in Doc A's Appendix C |
| Question | `Q-###` | `Q-004` | An open question carried across sessions |
| Work item | `WI-S###-NN` | `WI-S001-03` | A single unit of work inside a session |

---

## 1. Current status snapshot

*Update at every checkpoint. Keep to one screen.*

```
Date:                2026-09-14
Last session:        — (not started)
Current phase:       Phase 1 — Audit & Baseline
Branch:              —
Last commit:         —
Working tree:        clean
pytest -q:           — (to be measured in Phase 1)
Prompt suite:        — (to be measured in Phase 1)
KG version:          — (to be established in Phase 3g)
Open bugs:           0
Open investigations: 0
Open questions:      0
Next action:         Start Phase 1, task 1.1 — untrack personas.yaml
```

---

## 2. Registers

*Indices, not history. Updated in place at every checkpoint. State changes are recorded in the session entry in §4, not here.*

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

*Decisions made during a session that are not yet in Doc A's Appendix C. Promote to Doc A when stable.*

| ID | Date | Session | Decision | Rationale | Proposed for Doc A? |
|---|---|---|---|---|---|
| *(none yet)* | | | | | |

### 2.4 Open questions register

| ID | Raised | Session | Question | Owner | State |
|---|---|---|---|---|---|
| *(none yet)* | | | | | |

**State values:** open · resolved (→ decision ID) · abandoned

---

## 3. Test taxonomy (reference)

Every work item in §4 names the kind of testing used.

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

## 4. Session entries

*Newest at the top. One entry per session.*

### 4.0 Session entry template

````markdown
### S### — YYYY-MM-DD — {short title}

**Phase:** {Doc A phase and section}
**Branch:** `{branch}`
**Session goal:** {one sentence}
**Outcome:** {completed / partial / blocked}

---

#### Work items

##### WI-S###-01 — {title}

| Field | Value |
|---|---|
| Type | bug · feature · refactor · investigation · test · doc |
| Test kind(s) | {from §3} |
| Doc A reference | {phase, section} |
| Bug ID | {B-### or —} |
| Investigation ID | {INV-### or —} |
| State | {open · fixed · verified · deferred} |

**Symptom / objective.**
{What was wrong, or what was being built. One paragraph.}

**Where observed.**
{Prompt, test, file, or log line that surfaced it.}

**Investigation.**
{Numbered steps. What was tried, what was ruled out, what was learned.}

1. {step}
2. {step}
3. {step}

**Commands and output.**

```bash
$ {command}
{output}
```

```bash
$ {command}
{output}
```

**Root cause.**
{One paragraph. The mechanism, not the symptom.}

**Fix.**
{What changed. Files and lines.}

**Test that proves it.**
{Test file, test name, what it asserts.}
- Test kind: {from §3}
- Without fix: {fails / passes}
- With fix: {passes}

**Evidence.**

*Deterministic:*
```
$ pytest -q {test_path}
{output}
```

*Probabilistic (if applicable):*
```
$ for i in $(seq 1 20); do ... done
{Runs: 20
  correct: 19 (95%)
  incorrect: 1 (5%)}
```

*Byte-equality (if applicable):*
```
$ diff docs/audit/golden/{file}.txt /tmp/after.txt
{empty}
```

**Files touched.**
- `{path}` — {what changed}
- `{path}` — {what changed}

**Commits.**
- `{sha}` — {message}

**Cross-references.**
- Relates to: {B-### / INV-### / WI-###}
- Doc A section: {§X.Y}
- Follow-up: {what remains}

---

#### Phase status update

- Phase Index row for {phase}: {state change}
- Doc A §{N}.7 Status section: {updated / not yet}

#### Blockers / open questions

- {Q-###: question}
- {blocker}

#### Next session should

- {bullet}
- {bullet}

#### Commits on branch

- `{sha}` — {message}
- `{sha}` — {message}