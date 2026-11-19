# SQL-EMITTER-FILES — index of `docs/plan/`

**Purpose:** one-line-per-file map of this folder. What each file is, what it owns, what it does *not* own, and the order to read them. This is an index, not a summary — the files carry their own detail.

**Folder scope:** the KG schema corpus work (Phase 1 design, Phase 2 data collection, the role maps, the pending register, the discovery method) plus the project rulebook. It does **not** hold the SQL emitter's source (that lives under `src/spire/rendering/`).

---

## The six files

| File | One line |
|---|---|
| `WORKING_STYLE.md` | The project rulebook — every session reads it first. |
| `SCHEMA_DISCOVERY_METHOD.md` | The reusable procedure for inventorying a new Fusion module against the pod. |
| `HANDOVER_KG_SCHEMA.md` | Phase 1: the strategy and design for moving physical column names out of `sql_overlay.py` into the KG. |
| `HANDOVER_KG_SCHEMA_PHASE2.md` | Phase 2: what Tasks 1–3 found on the pod, the reversals, and the first six role maps. |
| `KG_ROLE_MAPS.md` | The drafted role maps — one section per entity, the seed data for the KG build. |
| `PENDING_KG_SCHEMA_CORPUS.md` | The pending-work register — remaining role maps, the §3.1–3.3 build, deferred questions. |

---

## Per file

### `WORKING_STYLE.md`

**Owns:** the standing rules — communication, branching, approval, the patch/verify contract (§15.3–§15.4), the S0–S11 evidence standard, log analysis, dev/runtime separation. Read at the start of every session.

**Does not own:** anything KG-specific. It is domain-neutral and applies to every window.

### `SCHEMA_DISCOVERY_METHOD.md`

**Owns:** the *method* — the three-layer strategy (objects → columns → relationships), capture discipline, the six failure modes, the copy-paste cell templates.

**Does not own:** the *work* — no per-entity findings. It is reusable across modules; the findings live in the Phase 2 handover and `KG_ROLE_MAPS.md`.

### `HANDOVER_KG_SCHEMA.md` (Phase 1)

**Owns:** the strategy (§1) and design (§3) — `kg_entity.fusion_table`, `kg_sql_column`, the build step, the emitter change, and what goes away. Still authoritative for the design.

**Does not own:** pod findings (those are Phase 2) or drafted role maps. It records the *discarded* runtime-gate approach as historical context — do not build from it.

### `HANDOVER_KG_SCHEMA_PHASE2.md`

**Owns:** what the pod actually contains (the R-1…R-8 reversals of Phase 1's assumptions), Task 1–3 status, and the first six role maps (Supplier module + Buyer). Also the Phase-2-resolved questions Q2/Q3/Q4/Q6.

**Does not own:** the Procurement role maps drafted after it (they are in `KG_ROLE_MAPS.md`), or the pending work (that is `PENDING_KG_SCHEMA_CORPUS.md`).

### `KG_ROLE_MAPS.md`

**Owns:** the drafted role maps, one `### <Entity>` section each — `kg_entity` row, `base_joins`, the `kg_sql_column` table, the `kg_derived_projection` table where present, bugs fixed, join-key verification, observations. Append-only; corrections are new sections referencing the old. Its header carries the drafting rules (never trust the sweep; verify every column and join key; cite substitutions; flag NULL-returning roles).

**Does not own:** the build, the pending list, or the method. It is the *data* the build consumes.

### `PENDING_KG_SCHEMA_CORPUS.md`

**Owns:** the pending-work register — status snapshot, the 11 remaining Receivables role maps with known trouble spots, the §3.1–3.4 build, the §3.3 emitter change, the known nullable join keys, the deferred questions (Q1/Q5), and the recommended order of work.

**Does not own:** what is already done (the handovers and `KG_ROLE_MAPS.md`). It records what is left.

---

## Reading order

1. `WORKING_STYLE.md` — the rules, every session.
2. `PENDING_KG_SCHEMA_CORPUS.md` — where the work stands and what is next.
3. `HANDOVER_KG_SCHEMA.md` §1, §3 — the strategy and design, still authoritative.
4. `HANDOVER_KG_SCHEMA_PHASE2.md` §1 — the pod reversals; then §3 for the first role maps.
5. `KG_ROLE_MAPS.md` — the drafted data, per entity.
6. `SCHEMA_DISCOVERY_METHOD.md` — when drafting a new entity, the procedure.

---

*End of index.*
