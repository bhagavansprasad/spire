# SPIRE — Session Handoff, 2026-10-01 (window 29, bundle reorg)

**Scope of this handoff.** Window 29 reorganised the context-bundle
configuration: `plan` was split into three bundles by intent — plan
(current state), reference (lookup material), history (the record).
Added a bundle-manifest tripwire that fails the suite when a tracked
file is not in any bundle. No code changed; the SQL Overlay POC
remains at phase 1 (data gathering for the Fusion DB schema).

**Read this first.** Then `docs/plan/WORKING_STYLE.md` (R + S0–S11,
rules 15.1/15.2/15.3), then `docs/design/SQL_OVERLAY_POC.md` (the POC's
own doc).

---

## Where we are

**Integration branch:** `hardening-master-v2`. Tip `db40182` (smoke
bundle added).

**Current working branch:** `poc/sql-overlay` — cut from
`hardening-master-v2` at `db40182`. Six commits, pushed, no PR yet.
Phase 0 of the POC done; phase 1 pending.

**Master:** `36cc3b8`. Frozen.

**Pod:** `fa-euth-dev49` (persona `default_dev` in `personas.yaml`).
Shell `IKS_FUSION_*` env vars reconciled with the persona in window 28;
both now on the same pod.

**Test suite:** 1279 passed, 1 skipped, 22 deselected. Plus 2 new
bundle-manifest tests.

---

## What window 29 did

**Bundle config catch-up.** `context_bundles.yaml` was missing six
entries: the F-058 and F-059 findings, the F-058 fix file, the SQL POC
doc (root and plan), and the F-058 test. All were added in window 27 or
28 by windows that did not update the config. This is the same class of
drift the phase-1 audit documents for the KG — a hand-maintained
registry of the "what exists" fact.

**Bundle-manifest tripwire.** `tests/test_bundle_manifest.py` — two
tests, both directions:

  1. Every tracked file not excluded (or allowlisted) is in some bundle.
  2. Every path named by a bundle exists in the working tree.

`git ls-files` is the authoritative tree, so gitignored scratch
(`trash/`, `context_out/`) is not flagged. Allowlist is deliberately
small: `LICENSE`, plus `__init__.py` markers by pattern.

**Bundle reorg — plan split three ways.** The `plan` bundle had grown
to ~40 files and 133k tokens, most of it the accumulated history of
every past fix. Split by intent:

| bundle | purpose | files | tokens |
|---|---|---|---|
| `plan` | current state; read every session | 7 | 31k |
| `reference` | lookup material; grep, do not read whole | 3 | 102k |
| `history` | the record; never loaded first | 55 | 331k |

The rule, stated in the yaml itself:

  current state       -> plan       (always loaded)
  lookup material     -> reference  (loaded on demand)
  record of past work -> history    (never loaded first)

`WORKING_STYLE.md` stays in `plan` — read every session.

---

## What's open

**SQL Overlay POC — phase 1 (data gathering).** Blocked on the Fusion
DB schema for the Supplier module. Needed from the user:

- Table names and joins for the five REST entities (Supplier, Address,
  Site, Classification, Contact).
- Column mappings for ~15 fields a WHERE or SELECT would name.
- One worked REST call and its DB SQL equivalent.

Any of the three, in any order. Item 1 is enough to start phase 2 (KG
<-> Fusion mapping).

**F-056 — three sources disagree.** Fix file
`docs/phase-2/fixes/F-056.md` reads `in-progress`; finding reads
`fixed`; FIX_PLAN §5.1 row reads `fixed | — | 2026-09-28`, no PR.
Next session should check whether the fix is on `hardening-master-v2`
and either open the PR or flip the row.

**F-059's S11 additions are not landed.** Three prompt files
(`prompts/dipstick/verify.txt`, `prompts/supplier/verify.txt`,
`prompts/procurement_supplier/verify.txt`) need repeated-run probes.
No fix to ride — small standalone branch.

**The release-gate litmus test.** A 10-prompt set spanning the four
modules, run before every delivery message. Not started. A branch
`feat/release-gate-litmus` exists — worth checking whether it already
carries work.

**Runtime clone.** `~/pocs/spire-runtime` still tracks
`hardening-master` (v1, retired). Deliberate update to
`hardening-master-v2` pending; not performed.

**Doc B model residual.** Three files sit in `history` that were the
skeleton of the old Doc A / Doc B two-document model:
`docs/plan/Doc_B_Index.md`, `docs/plan/Phase_02_Correctness.md`,
`docs/plan/TEMPLATE_Session_Entry.md`. Current practice uses
findings (`docs/audit/findings/`) and fix files
(`docs/phase-2/fixes/`) instead. `WORKING_STYLE.md` §13 still names
the Doc B model — a future edit reconciles the two or removes the
section.

---

## Agenda for the next window

1. **SQL Overlay POC phase 1.** Receive the Fusion schema (Supplier
   module), run phase 2 (KG <-> Fusion mapping), then phase 3 (overlay
   tables + seed + loader). The POC plan is in
   `docs/design/SQL_OVERLAY_POC.md` §Phases.
2. **F-056 reconciliation.** Cheap; starts the window cleanly while
   the schema arrives.
3. **F-059 S11 additions.** Small standalone branch.
4. **Litmus test.** Check `feat/release-gate-litmus` first.

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
  They can drift and 401 while the pipeline is fine.
- **Intermittent shapes need N>=20 before classification.**
- **No LLM in SQL emission.** The Plan is a KG lookup; the SQL is the
  Plan.
- **Bundle rule for future splits:** current state -> plan; lookup
  material -> reference; record of past work -> history. The
  bundle-manifest tripwire enforces existence, not categorisation.

---

*End of handover.*
