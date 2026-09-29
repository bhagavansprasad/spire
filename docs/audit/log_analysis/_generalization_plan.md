# Log-analysis generalization plan

**Status:** planning. Not started. Next window's work.
**Created:** 2026-09-27
**Depends on:** `docs/audit/log_analysis/_plan.md` (the pipeline as it exists
today), `scripts/log_analysis.py` (the helper as it exists today).

---

## 1. Why this document exists

The pipeline in `_plan.md` and the helper at `scripts/log_analysis.py`
are **smoke-shaped**. They work for the smoke round they were built on
and for nothing else as written. Every concrete path names a smoke file:

- `_plan.md` Step 3, Step 4, Part D, Part E all say `smoke.log`.
- `scripts/log_analysis.py` hardcodes `smoke.log` in `cmd_signatures`
  and `cmd_classify`, and `_triad` names `smoke.log` too.

Run this pipeline against a `verify` round and it fails at the first
file read. Run it against an `exhaust` round and it fails the same way.

**What the plan should be.** Tier-agnostic. Open any round folder
produced by `promptkit.py`, discover its structure, and proceed. The
tier (`smoke` / `verify` / `exhaust`) is a property of the run that
lives in its manifest; the pipeline reads it, does not assume it.

**Why this matters.** The plan's value is that a new analyst can hand
it a round and get findings out. If it only works on smoke, the other
two tiers have no pipeline. That is most of the pipeline's value
missing.

---

## 2. The three concrete changes

### 2.1 Doc — Step 1 becomes *Discover the round's structure*

Currently Step 1 is "Confirm the round exists and matches its
manifest" - a structural check against an assumed shape. Rewrite it to
*discover* the shape:

- Open the round folder.
- Read `_manifest.yaml`. Extract `tier`. (Confirm the manifest key
  name - see Open Question Q1.)
- List the actual file names inside one set folder.
- Record them in `RUN.md`: the round's tier, and the naming pattern
  for its three per-set files.
- Every downstream step uses the discovered names.

Step 1's gate becomes: "the round is understood, and its structure is
recorded". A round whose set-folder file names do not match any known
pattern stops here and is reported.

### 2.2 Doc — abstract paths

Replace concrete `smoke.log` with `<tier>.log` in:

- Step 3 (signatures)
- Step 4 (classify)
- Step 5 (regression cross-check)
- Part D templates (`RUN.md`, `<set>.md`)
- Part E subcommand reference

Part G keeps `smoke.log` - it names an actual smoke round.

Add one sentence in Part A: "The tier is a property of the run,
declared in `_manifest.yaml`. Every path in this document is
`<tier>.log`; the actual tier comes from the manifest."

### 2.3 Script — read the manifest

`_round_root` currently just checks the folder exists. Change it to:

- Read `_manifest.yaml` in the round folder.
- Extract `tier`.
- Attach `tier` to `args` so every subcommand can build
  `f"{tier}.log"` instead of the literal `"smoke.log"`.
- If the manifest cannot be read or has no `tier` key, fail loudly
  rather than defaulting.

Two functions to change: `_round_root` (or a new
`_load_round_manifest`), and the two commands that read per-set logs
(`cmd_signatures`, `cmd_classify`). `_triad` should take the tier.

No `--tier` flag. The manifest is the source of truth; a flag invites
drift.

---

## 3. Open questions to resolve first

Before writing any code, answer these. Several change the shape of
the change.

**Q1 - What key in `_manifest.yaml` carries the tier?**
The manifest has not been inspected for this. Read one before
planning. If the key is `tier: smoke`, the change is trivial. If the
tier is implied only by the set-name suffix (`dipstick/smoke`), the
script must derive it, not read it.

**Q2 - Is the per-set file naming always `<tier>.log` / `<tier>.txt` /
`<set>_summary.log`?**
The smoke round uses this. A verify round probably does too, but
"probably" is not the standard. Inspect one verify run's folder.

**Q3 - Is the round-level `_summary.log` column format stable?**
The script's exit-code regex was written for the wrong format once
already; it was fixed by inspection. Before the refactor, confirm
`set / exit / secs / status` is the format for every tier. If it
varies, the parse needs to be schema-aware.

**Q4 - Does the plan apply only to `promptkit.py` runs, or to any log
tree?**
Promptkit runs are the current use case. But the pipeline's shape
(discover structure, triage, signatures, classify, candidates, gate,
R, S0-S11, findings) is not promptkit-specific. A pytest log, a
manually-run tester sweep, or a future tool's output could use the
same pipeline. Decide whether the plan claims to support only
promptkit runs, or claims to support any run that provides a
manifest and set folders. The answer changes Step 1's gate.

**Q5 - Should the tier come from the manifest, the run_id, the path,
or the set name?**
The run_id is `20260925_150333` - no tier in it. The path is
`overnights/<run_id>/` - no tier. The set folders are
`<set>/smoke.log` - tier in the file name. The manifest is the only
place where the tier is a first-class property. Confirm this is where
it should be read from.

**Q6 - What if a run mixes tiers in one folder?**
Today every smoke round has only smoke sets. A future "mixed sweep"
might hold smoke and verify sets in one round. If that is planned,
Step 1 must read the tier per set, not per round.

**Q7 - What breaks when a signature pattern is tier-specific?**
The signature list in the script is a flat list today. A signature
that only makes sense for smoke (e.g. a smoke-only JSON-mode artifact)
would surface in a verify round as noise. Decide: one list for all
tiers, or a per-tier list.

**Q8 - Where does the generalization live - in this doc, or as a
rewrite of `_plan.md`?**
Two options. (a) Keep `_plan.md` as the smoke-flavored description and
add a `_generalization.md` that supersedes it. (b) Rewrite `_plan.md`
in place, tier-agnostic from the start, and delete the smoke-specific
sentences. (b) is cleaner; (a) preserves history. The next window
should pick one.

---

## 4. Scope of the change

**In scope:**

- Rewrite Step 1 of `_plan.md` as structure-discovery.
- Replace concrete `smoke.log` with `<tier>.log` in the abstract
  sections.
- Change `scripts/log_analysis.py` to read the tier from the manifest.
- Add a `RUN.md` field: `structure: <the discovered per-set file
  names>`.
- Update Part E's subcommand reference to reflect the manifest read.

**Out of scope:**

- Changing the pipeline's fourteen-step order or the S0-S11 standard.
- Adding new subcommands to the script.
- Any change to the findings/ or the archive.
- Any change to the smoke round's existing artifacts. It already
  names `smoke.log` and correctly so.

---

## 5. Next window - order of work

1. **Read one `_manifest.yaml`.** Answer Q1 and Q5 with the file
   contents, not a guess.
2. **Read one verify round's folder.** Answer Q2 and Q3.
3. **Decide Q4** (promptkit-only or universal).
4. **Decide Q6** (per-round tier vs per-set tier).
5. **Decide Q7** (signature list per-tier or flat).
6. **Decide Q8** (rewrite in place or supersede).
7. **Apply the three changes** (doc Step 1, doc abstract paths,
   script manifest read).
8. **Regression test:** run the script against the smoke round and
   confirm every subcommand still works. Then against a verify round
   if one exists.

---

## 6. Non-goals

This document is not a plan. It is the *record of intent* so the next
window does not rediscover the problem from scratch. The plan is
`_plan.md`; this file explains why and how the plan needs to broaden.

If the next window decides the plan should stay smoke-shaped and add
a sibling `verify.md` / `exhaust.md`, that is a valid outcome - but it
should be a decision, not a default.
