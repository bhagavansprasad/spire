# Spire Enhancement — Status Tracker

Tracks progress against `docs/spire_enhancement_requirements.md` v1.0.
That document is the frozen spec; this file is the living record of what
has actually been done. Update this file at the end of any session that
touches a phase — do not edit the requirements doc itself to reflect
progress.

**Last updated:** 2026-07-30 (evening session)

---

## Phase status

| Phase | Requirements | Status | Notes |
|---|---|---|---|
| 0 | (four pre-existing defects, not in the requirements doc) | ✅ Done | Merged. See handoff 2026-07-30 evening. |
| 1 | UX-05, OBS-01, OBS-02 | ⬜ Not started | **Next up.** |
| 2 | UX-01, UX-02, UX-03 | ⬜ Not started | |
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
