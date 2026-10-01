# SPIRE — Session Handoff, 2026-10-01 (window 28, SQL overlay POC opened)

**Scope of this handoff.** Window 28 opened the **SQL Overlay POC** —
a deterministic projection of the Plan into Fusion-DB SQL, printed
alongside the existing pipeline answer. Phase 0 (POC doc, scope,
branch) landed. Phase 1 (data gathering — Fusion DB schema for the
Supplier module) is the next action. The window also reconciled the
shell env vars with the persona (both now on `fa-euth-dev49`), and
settled two design questions: no LLM in SQL emission, and no
REST-vs-DB data comparison in this POC.

**Read this first.** Then `docs/plan/WORKING_STYLE.md` (R + S0–S11,
rules 15.1/15.2/15.3), then `docs/fixes/FIXES.md` (the playbook), then
`docs/design/SQL_OVERLAY_POC.md` (the POC's own doc).

---

## Where we are

**Integration branch:** `hardening-master-v2`.
**Tip:** `db40182` — smoke bundle added (window 28).

**Current working branch:** `poc/sql-overlay` — one commit above
`hardening-master-v2`, holding `docs/design/SQL_OVERLAY_POC.md`
(phase 0). Pushed to origin, no PR yet. PR opens when the POC
completes.

**Master:** `36cc3b8`. Frozen.

**Pod:** `fa-euth-dev49` (persona `default_dev` in `personas.yaml`).
The shell `IKS_FUSION_*` env vars now agree with the persona; both
were reconciled this window. They are separate paths and can drift —
see Rules below.

**Test suite:** 1279 passed, 1 skipped, 22 deselected.

**Local-only convention:** `trash/` at repo root is gitignored. All
rule-15.1 captures live there.

---

## What window 28 did

1. **Environment reconciliation.** Shell env was on `dabpqy` /
   `Angus.Cooper` while the persona was on `fa-euth-dev49` /
   `Sean.Walker`. The 401s that looked like pod trouble were the shell
   credential. Both now on `fa-euth-dev49`. The pipeline was never
   affected — it reads the persona, not the env vars.

2. **SQL capability question answered.** SPIRE today emits Fusion
   REST, not SQL. The plan's §1 states SQL is the original target and
   the current build is the platform being built toward it. No SQL
   exists in code yet.

3. **SQL emission design settled.** Deterministic projection of the
   Plan. **No LLM in SQL emission.** The model's job ends at the
   Intent; the Plan is a KG lookup; the SQL is the Plan in a different
   syntax. Anything else would reintroduce the failure class SPIRE was
   built to eliminate (LLM guessing joins and columns).

4. **SQL Overlay POC opened.** `docs/design/SQL_OVERLAY_POC.md`
   committed to `poc/sql-overlay` (phase 0). Scope: Supplier module
   only, print-only, no execution, no REST-vs-DB comparison. Three
   overlay tables (`kg_sql_entity`, `kg_sql_field`, `kg_sql_filter`)
   seeded from the real Fusion schema, plus a deterministic emitter and
   a `--show-sql` flag on `promptkit.py`.

---

## What's open

**SQL Overlay POC — phase 1 (data gathering).** Blocked on the Fusion
DB schema for the Supplier module. Needed from the user:

- Table names and joins for the five REST entities (Supplier, Address,
  Site, Classification, Contact).
- Column mappings for ~15 fields a WHERE or SELECT would name
  (`SupplierId`, `SupplierNumber`, `Supplier`, `Status`,
  `BusinessRelationship`, `TaxpayerCountryCode`, `CreatedBy`,
  `CreationDate`, `LastUpdatedBy`, `LastUpdateDate`, plus child PKs and
  FKs).
- One worked REST call and its DB SQL equivalent.

Any of the three, in any order. Item 1 is enough to start phase 2.

**F-056 — three sources disagree.** Fix file
`docs/phase-2/fixes/F-056.md` reads `in-progress`; finding reads
`fixed`; FIX_PLAN §5.1 row reads `fixed | — | 2026-09-28`, no PR
number. The next session should check whether the fix is on
`hardening-master-v2` and either open the PR or flip the row.

**F-059's S11 additions are not landed.** Three prompt files
(`prompts/dipstick/verify.txt`, `prompts/supplier/verify.txt`,
`prompts/procurement_supplier/verify.txt`) need repeated-run probes.
No fix to ride — small standalone branch.

**The release-gate litmus test.** A 10-prompt set spanning the four
modules, run before every delivery message. Not started as a POC; a
branch named `feat/release-gate-litmus` exists — worth checking whether
it already carries work. The morning delivery message that started
window 26 needs reframing once the litmus set is proven.


**Runtime clone.** `~/pocs/spire-runtime` still tracks
`hardening-master` (v1, retired). Deliberate update to
`hardening-master-v2` pending; not performed this window.

---

## Agenda for the next window

1. **SQL Overlay POC phase 1.** Receive the Fusion schema (Supplier
   module), run phase 2 (KG <-> Fusion mapping), then phase 3 (overlay
   tables + seed + loader). The POC plan is in
   `docs/design/SQL_OVERLAY_POC.md` §Phases.
2. **F-056 reconciliation.** Cheap; starts the window cleanly while
   the schema arrives.
3. **F-059 S11 additions.** Small standalone branch; the rule added in
   #184 says they land with the finding, but F-059 has no fix to ride.
4. **Litmus test.** If the SQL POC is on hold, the litmus set is the
   other pending deliverable. Check `feat/release-gate-litmus` first.

---

## Rules that keep biting

- **One command at a time (rule 2.1: split on uncertainty, not
  count).**
- **Every file edit is two cells — Python script, then shell
  verification (rule 15.3).**
- **Capture complete output to a file, then grep (rule 15.1).**
- **`~~~` for any outer fence whose content contains triple backticks
  (rule 4).**
- **Name a slow command's cost (rule 15.2).**
- **Branch-first for fixes; PR into `hardening-master-v2` (rule 10).**
  Nothing merges to `master` without explicit user instruction.
- **V0 first — the fix file (or POC doc) is committed before any source
  file.**
- **S11 prompts land with the finding or the fix, not just listed in
  the fix file (the rule added in #184).**
- **Shell `IKS_FUSION_*` env vars are a separate path from the persona.**
  They can drift and 401 while the pipeline is fine — this cost two
  turns in window 27. Confirm both point at the same pod before
  trusting a curl that verifies a pipeline result.
- **Intermittent shapes need N>=20 before classification.** F-059 was
  filed on N=5 and closed on N=20. The threshold is not optional.
- **No LLM in SQL emission.** The Plan is a KG lookup; the SQL is the
  Plan. The model's job ends at the Intent.

---

*End of handover.*
