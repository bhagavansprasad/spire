# SPIRE — Session Entry Template

Copy this block when starting a new session. Fill it in. Paste the filled
entry at the TOP of the current phase file.

---

### S### — YYYY-MM-DD — {short title}

**Phase:** {Doc A phase and section}
**Branch:** `{branch}`
**Session goal:** {one sentence}
**Outcome:** {completed / partial / blocked}

**Inputs received this session:** {bundles, prior session decisions}

**Outputs:** {what this session produced}

---

#### Work items

##### WI-S###-01 — {title}

| Field | Value |
|---|---|
| Type | bug · feature · refactor · investigation · test · tooling · doc |
| Test kind(s) | {from index §3} |
| Doc A reference | {phase, section} |
| Bug ID | {B-### or —} |
| Investigation ID | {INV-### or —} |
| State | {open · fixed · verified · deferred} |

**Symptom / objective.** {One paragraph.}

**Where observed.** {Prompt, test, file, or log line.}

**Investigation.** {Numbered steps.}

1. {step}
2. {step}

**Commands and output.** Paste each command and its raw output.

**Root cause.** {One paragraph. The mechanism, not the symptom.}

**Fix.** {What changed. Files and lines.}

**Test that proves it.** {Test file, test name, what it asserts.}
- Test kind: {from index §3}
- Without fix: {fails / passes}
- With fix: {passes}

**Evidence.** Deterministic: pytest output. Probabilistic: N≥20 distribution.
Byte-equality: diff result.

**Files touched.**
- `{path}` — {what changed}

**Commits.**
- `{sha}` — {message}

**Cross-references.**
- Relates to: {B-### / INV-### / WI-###}
- Doc A section: {§X.Y}
- Follow-up: {what remains}

---

#### Phase status update

- Phase Index row: {state change}
- Doc A §{N}.7 Status section: {updated / not yet}

#### Blockers / open questions

- {Q-###: question}

#### Next session should

- {bullet}

#### Commits on branch

- `{sha}` — {message}
