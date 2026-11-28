# SME prompt status — index and how to add a run

Tracking surface for the 40-prompt **SME Module A** litmus set
(`prompts/sme_module_a/sme_module_a_litmus.txt`). One folder so that a run's
results, the outstanding fix queue, and the cross-run comparison live
together instead of being scattered across window summaries.

## Files

| File | Kind | Purpose |
|---|---|---|
| `README.md` | living | this index |
| `run01_2026-11-21_results.md` | **immutable** | first recorded run |
| `run02_2026-11-28_results.md` | **immutable** | second recorded run |
| `FIX_PLAN.md` | living | cumulative open-issue queue, grouped by root cause |
| `COMPARISON.md` | living | per-prompt status across every run |
| `HANDOFF.md` | living | context needed to resume in a new window |

**Why the split.** A run result is a historical fact — it must never be
edited after the fact, or the comparison stops meaning anything. The fix
plan and the comparison are cumulative by nature and get updated every
cycle. One run → issues → fix plan → fixed → next run → …

## Naming

```
runNN_YYYY-MM-DD_results.md
```

`runNN` is zero-padded so a directory listing sorts chronologically, and the
date follows so the file is self-describing outside the folder.

## Run history

| Run | Date | Prompts | OK | Refused | Pod/error | Bad SQL | Log |
|---|---:|---:|---:|---:|---:|---:|---|
| run01 | 2026-11-21 | 40 | 11 | 18 | 0 | 10 | `evidence/t_f081_litmus_run.txt` |
| run02 | 2026-11-28 | 40 | 13 | 17 | 10 | 0 | `evidence/t_f076_litmus_run.txt` |

*Pod/error* = ran but could not return data for an environment reason
(HTTP 403, a collection returning 0 rows) rather than a Spire reason. It is
counted separately from *Refused* on purpose — see `COMPARISON.md`.

## Status codes

Every per-prompt row in this folder uses one of five codes. They are
deliberately fine-grained: collapsing `ERR403` or `ZERO` into `FAIL` would
blame the code for an environment change.

| Code | Meaning | Whose problem |
|---|---|---|
| `OK` | answered, at least one row | — |
| `ZERO` | ran, returned no rows | could be pod data or a wrong filter — check |
| `REFUSED` | Spire declined to answer | Spire (unless marked *legitimate*) |
| `ERR403` | the REST call failed (403) | Fusion user's access — **not** code |
| `BADSQL` | emitted SQL contained an invalid `-- unmapped` fragment | Spire |

`BADSQL` is retired: it was zero in run02 after F-078, so any reappearance is
a regression.

## Where the raw logs live

Run logs are evidence, not source — they are gitignored under `evidence/`.
The two logs referenced above are:

```
evidence/t_f081_litmus_run.txt   # run01, 2026-11-21
evidence/t_f076_litmus_run.txt   # run02, 2026-11-28
```

`evidence/` is untracked by design (9 MB of captures). To reproduce a run:

```bash
export PATH="/home/bhagavan/virtenv/spire/bin:$PATH"   # fastmcp must resolve
./spire-host.sh --start dev
SPIRE_MCP_URL=http://127.0.0.1:4001/mcp/ \
  python scripts/promptkit.py --run \
    --prompt-file prompts/sme_module_a/sme_module_a_litmus.txt \
    --show-parser --show-planner --show-sql --show-synthesizer \
    > evidence/t_<tag>_litmus_run.txt 2>&1
```

## Adding a run

1. Run the set (command above), writing the log into `evidence/`.
2. Create `runNN_YYYY-MM-DD_results.md` from the previous run's file as the
   template — **do not edit any earlier `runNN_` file**.
3. Update `COMPARISON.md` with the new column and the trend against the
   previous run.
4. Update `FIX_PLAN.md`: close what the run proves fixed, add what it newly
   surfaces, re-confirm statuses.
5. Update `HANDOFF.md` and this file's run-history table.

## Related

- `docs/fixes/FIX_PLAN.md` — the F-0xx defect register; this folder's
  `FIX_PLAN.md` is the prompt-set view of the same work and cross-links there.
- `prompts/sme_module_a/sme_module_a_expected.md` — the **predicted** status
  per prompt, from declared KG capabilities. Prediction ≠ observation; when
  they disagree, the disagreement is the finding.
- `prompts/sme_module_a/PROMPT_SHEET_2026-11-21.md` — fill values and
  readiness at capture time.
