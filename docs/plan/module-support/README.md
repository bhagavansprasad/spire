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
| 4 | the module file you are working on (`<family>/<module>.md`) | that module's boundary, sub-modules, decisions, coverage |
| 5 | [`MODULE_SUPPORT_PLAYBOOK.md`](./MODULE_SUPPORT_PLAYBOOK.md) §6.0 | the 29 touchpoints — read on demand, not end to end |

Resume a module in one line: **`PORTFOLIO_STATUS.md` → `<family>/<module>.md`
→ its branch.**

## What lives here

Shared, one copy for the whole portfolio:

| Path | Kind | Mutability |
|---|---|---|
| `README.md` | index | living — structure only |
| `PORTFOLIO_STATUS.md` | dashboard: every module and sub-module | living, dated |
| `MODULE_SUPPORT_ROADMAP.md` | portfolio, priority, gates | living |
| `MODULE_SUPPORT_PLAYBOOK.md` | the code procedure, 29 touchpoints | living |
| `PROBE_CATALOGUE.md` | module-independent investigation recipes | **append-only** |
| `MODULE_SUPPORT_MEETING_MINUTES.md` | shared discussion record, newest first | **append-only** |
| `AP_COVERAGE_ASSESSMENT.md` | dated evidence artifact (run02, unmerged-PR record) | **frozen** |
| `supplier.md` | the shared-master-data module; it belongs to no family | living |

Three family folders, **one file per module, no folders inside them**:

```
financials/  payables.md  receivables.md  gl.md  cash_management.md
             fixed_assets.md  sla.md
scm/         procurement.md  om.md  inv.md  wip.md  bom.md  cost_management.md
hcm/         global_hr.md  payroll.md  absence.md  benefits.md  otl.md  orc.md
```

Each module file holds, in this order: brief and sub-module list; MVP boundary
(gate 3); decisions `D-<MOD>-NNN`; coverage matrix and per-prompt verdicts;
known gaps and accepted refusals. A module file is named by its **routable
module id** when it has one (`payables`, not `ap`), so `grep payables` finds
the code, the KG rows, the parser context and the docs together. The business
name goes in the title. The 14 areas with no module id yet use a provisional
name that the gate-0 brief records.

Family folders hold no README. The folder listing is the index and
`PORTFOLIO_STATUS.md` is the dashboard; a fourth navigator would rot the way
`STATUS.md` did.

`STATUS.md` is retired once this file and `PORTFOLIO_STATUS.md` are on
`master` — its structure half is here, its dated half is there.

## Adding a module

1. Run gates 0–2 (roadmap §4): module brief, REST feasibility, prompt set.
2. Create `<family>/<module>.md` with the sub-module list and the MVP boundary
   (gate 3). **Every sub-module is a row in that one file, not a file.**
3. Record the boundary decisions in the same file, as `D-<MOD>-NNN` rows.
4. Work the touchpoints in playbook §6.0, top to bottom.
5. Add the module's rows to `PORTFOLIO_STATUS.md`; register the new file in
   `docs/README.md` **and** `context_bundles.yaml`
   (`tests/test_bundle_manifest.py` fails otherwise — it matches exact paths,
   so a bundled directory will not cover a new file).

A module gets a directory only when a single file stops being workable —
sustained growth past a few hundred lines, or a second artifact type such as a
per-sub-module acceptance note. A new family folder is created when its first
module starts, not in advance.

## Rules

- **Nothing dated belongs in this file.** If a line needs editing when the pod
  changes, it is in the wrong document.
- A decision that changes scope gets a `D-<MOD>-NNN` row **in the same commit
  as the change it authorises**, appended at the end of the decisions section.
  Chat is not a record. An overturned decision is marked
  `superseded by D-<MOD>-NNN`, never rewritten.
- Investigation recipes that are not module-specific belong in
  `PROBE_CATALOGUE.md`, so the next module does not rediscover them.
- Run `pytest tests/test_bundle_manifest.py` after adding or moving a doc.
