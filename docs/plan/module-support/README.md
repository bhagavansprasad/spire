# Module support — start here

How Spire grows from partially-supported Fusion modules to measured, honest
module support. **Structure and navigation only** — priorities live in the
roadmap, live state in the portfolio status.

## Reading order

| Order | Document | Why |
|---:|---|---|
| 1 | this file | where things are |
| 2 | [`PORTFOLIO_STATUS.md`](./PORTFOLIO_STATUS.md) | which module and sub-module is where, right now |
| 3 | [`MODULE_SUPPORT_ROADMAP.md`](./MODULE_SUPPORT_ROADMAP.md) | priority, the eight gates, open decisions |
| 4 | the module folder you are working on (`<module>/README.md`) | that module's boundary, decisions, coverage |
| 5 | [`MODULE_SUPPORT_PLAYBOOK.md`](./MODULE_SUPPORT_PLAYBOOK.md) §6.0 | the 29 touchpoints — read on demand, not end to end |

Resume a module in one line: **`PORTFOLIO_STATUS.md` → the module's
`COVERAGE.md` → its branch.**

## What lives here

| Path | Kind | Mutability |
|---|---|---|
| `README.md` | index | living — structure only |
| `PORTFOLIO_STATUS.md` | dashboard: every module and sub-module | living, dated |
| `MODULE_SUPPORT_ROADMAP.md` | portfolio, priority, gates | living |
| `MODULE_SUPPORT_PLAYBOOK.md` | the code procedure, 29 touchpoints | living |
| `PROBE_CATALOGUE.md` | module-independent investigation recipes | **append-only** |
| `MODULE_SUPPORT_MEETING_MINUTES.md` | shared discussion record, newest first | **append-only** |
| `AP_COVERAGE_ASSESSMENT.md` | dated evidence artifact (run02, unmerged-PR record) | **frozen** |
| `<module>/README.md` | module brief, sub-module list, in/out boundary | living |
| `<module>/DECISIONS.md` | `D-<MOD>-NNN` decisions with why and evidence | **append-only** |
| `<module>/COVERAGE.md` | capability matrix, per-prompt verdicts, gaps | living, versioned |

`STATUS.md` is retired once this file and `PORTFOLIO_STATUS.md` are on
`master` — its structure half is here, its dated half is there.

## Adding a module

1. Run gates 0–2 (roadmap §4): module brief, REST feasibility, prompt set.
2. Create `<module>/README.md` with the sub-module list and the MVP boundary
   (gate 3). **Every sub-module is a row, not a file.**
3. Create `<module>/DECISIONS.md` and record the boundary decisions there.
4. Work the touchpoints in playbook §6.0, top to bottom.
5. Add the module's rows to `PORTFOLIO_STATUS.md`; register any new document
   in `docs/README.md` **and** `context_bundles.yaml`
   (`tests/test_bundle_manifest.py` fails otherwise).

A sub-module gets its own directory only when it gets its own branch.

## Rules

- **Nothing dated belongs in this file.** If a line needs editing when the pod
  changes, it is in the wrong document.
- A decision that changes scope gets a `DECISIONS.md` row **in the same commit
  as the change it authorises**. Chat is not a record. An overturned decision
  is marked `superseded by D-<MOD>-NNN`, never rewritten.
- Investigation recipes that are not module-specific belong in
  `PROBE_CATALOGUE.md`, so the next module does not rediscover them.
- Run `pytest tests/test_bundle_manifest.py` after adding or moving a doc.
