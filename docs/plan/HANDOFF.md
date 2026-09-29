# SPIRE — Session Handoff, 2026-09-29 (window 27, four-prompt triage closed)

**Scope of this handoff.** Window 27 closed the four-prompt triage that
window 26 opened. Two findings (F-058, F-059) were filed, walked
S0–S11, and resolved. One fix landed and merged (F-058, PR #185). One
closed as not-a-bug (F-059). The window also renamed the integration
branch (`hardening-master` → `hardening-master-v2`, per the v1 retirement
in #183), reconciled the FIX_PLAN ledger to F-059, and hardened the S11
rule so sibling prompts land with the finding, not just in the fix file.

**Read this first.** Then `docs/plan/WORKING_STYLE.md` (R + S0–S11),
then `docs/fixes/FIXES.md` (the playbook).

---

## Where we are

**Branch:** `hardening-master-v2`. The v1 branch (`hardening-master`) was
merged to `master` at PR #183 and retired. `hardening-master-v2` is the
current integration branch: phase branches spawn off it and PR back.

**Master:** `36cc3b8` — carries the v1 promotion (#183) and the
window-26 context-bundles update. Frozen.

**hardening-master-v2 tip:** `4496a84` — PR #185, the four-prompt triage.

**Pod:** `fa-euth-dev49` (persona `default_dev` in `personas.yaml`).
The `IKS_FUSION_*` shell env vars currently agree with the persona; both
are on the same pod as of this window. They are separate paths and can
drift — see Rules below.

**Test suite:** 1279 passed, 1 skipped, 22 deselected.

**Local-only convention:** `trash/` at the repo root is gitignored. All
rule-15.1 captures from window 27 landed there (`t_F058_*.txt`,
`t_F059_*.txt`, `t_test_3_open_pos_r.txt`). Not shared.

---

## What window 27 did

| # | prompt | window 26 | window 27 disposition |
|---|---|---|---|
| P1 | Count of suppliers | FAIL | F-059 closed-as-not-a-bug (N=20 clean) |
| P2 | Show PO 2144 and its lines | PASS | pass |
| P3 | Which suppliers have open POs? | FAIL | sibling under F-059 |
| P4 | Top 5 suppliers by spend this year | PARTIAL | F-058 fixed, verified (PR #185) |

**F-058 — period-anchored phrases on the aggregate path.**
Finding: `docs/audit/findings/F-058.md`. Fix file:
`docs/phase-2/fixes/F-058.md`. Fixed in
`src/spire/nl_parser/parser.py` (`_extract_period_bounds` + call site),
of the same class as `_extract_invoice_number` / `_extract_list_cap` /
`_has_country_column_phrasing`. PR #185, merged `4496a84`. Status:
`verified`.

**F-059 — Count of suppliers intermittently returns 0.**
Finding: `docs/audit/findings/F-059.md`. Closed as not-a-bug: N=20 runs
produced `There are 6575 suppliers.` on all 20. The morning empties
matched the documented 2026-07-17 "empty collection on a freshly-
provisioned pod" shape in the endpoints reference. Re-open if the same
prompt varies again, or if a change touches
`src/spire/mcp_server/tools/suppliers.py` or
`src/spire/fusion/client.py`.

**Ledger reconciled.** `FIX_PLAN.md` §5.1 now runs F-052 through F-059.
F-056 (window 25), F-057 (PR #180), F-058 (PR #185), F-059 (closed) added
in commit `799c172`. Section 5.1 previously stopped at F-055.

**S11 rule exercised for the first time.** F-058's sibling prompts landed
in `prompts/date_filters/verify.txt` section J — in commit `6d17861`,
alongside the F-058 finding rather than the fix, so the prompt set fails
red before the fix lands. Interpretation of the rule added on
`hardening-master-v2` in #184.

**Process note — F-059 filed below the threshold.** F-059 was filed on
N=5, below the standard's N≥20 threshold for intermittent shapes. Its
own S8 records the miss: had the threshold sweep been run before filing,
F-059 would not have existed. The smoke tier currently runs each prompt
once per sweep; that gap is named in F-059's S11 and is the fix that
would have prevented this.

---

## What's open

**F-056 — four-bucket synthesizer overrun.**
Fix file: `docs/phase-2/fixes/F-056.md`. V-standard walked in window 25.
Its `**State:**` line reads `in-progress`, its finding's `**Status:**`
reads `fixed`, and the FIX_PLAN row reads `fixed | — | 2026-09-28` — three
sources, two states, no PR number. The next session should:

1. Check whether the fix is on `hardening-master-v2` already:
   `grep -n "_supplier_pos_buyers" src/spire/synthesizer/p2p.py`.
2. If yes, open the PR to close it out and flip the row to
   `verified | #NNN`.
3. If no, locate the branch and open the PR from there.

**F-059's S11 additions are not landed.**
F-059's S11 names repeated-run probes in three prompt files
(`prompts/dipstick/verify.txt`, `prompts/supplier/verify.txt`,
`prompts/procurement_supplier/verify.txt`). None were landed — F-059 has
no fix, so there was no branch to land them on. Land them on their own
small branch, per the S11 rule.

**Runtime clone is unaffected but unchanged.**
`~/pocs/spire-runtime` still tracks `hardening-master` (v1), which is
retired. A deliberate update to point it at `hardening-master-v2` is
pending; the handoff does not perform it.

---

## Agenda for the next window

1. **F-056's PR.** Reconcile the three states and either open the PR or
   flip the row with the merge SHA. Small; starts the window cleanly.
2. **F-059's S11 additions.** Three prompt files, repeated-run probes,
   no fix code. Exercise the S11 rule on the branch that needs them.
3. **Whatever comes next from the strategy.** The plan's Phase 3
   (Consistency) has Phase 3a (prompt coverage validation) not started.
   The prompt-set reorg (Stage 3 in `docs/prompts/SURFACE.md`) is
   pending. Both are candidates.
4. **Do not re-open F-058 or F-059** unless their re-open conditions
   fire. F-058 is verified; F-059's condition is named above.

---

## Rules that keep biting

- **One command at a time (rule 2.1: split on uncertainty, not count).**
- **Every file edit is two cells — Python script, then shell
  verification (rule 15.3).**
- **Capture complete output to a file, then grep (rule 15.1).**
- **`~~~` for any outer fence whose content contains triple backticks
  (rule 4).**
- **Name a slow command's cost (rule 15.2).**
- **Branch-first for fixes; PR into `hardening-master-v2` (rule 10).**
  Nothing merges to `master` without explicit user instruction.
- **V0 first — fix file written and committed before any source file
  (FIX_PLAN §8 step 1).**
- **S11 prompts land with the finding or the fix, not just listed in
  the fix file (the rule added in #184).**
- **Shell `IKS_FUSION_*` env vars are a separate path from the persona.**
  They can drift from `personas.yaml` and 401 while the pipeline is fine
  — this cost two turns in window 27. Confirm both point at the same pod
  before trusting a curl that verifies a pipeline result.
- **Intermittent shapes need N≥20 before classification (R's clause).**
  F-059 was filed on N=5 and closed on N=20. The threshold is not
  optional.

---

*End of handover.*
