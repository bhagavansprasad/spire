# SME prompt set — handoff / resume context

Everything a new window needs to pick this work up without re-deriving it.
Read this, then `FIX_PLAN.md`, then the latest `runNN_` file.

**Last updated:** 2026-11-28 (after run02, and after this folder landed).

## Where things stand

| | |
|---|---|
| Base | `master` @ `f1a528a` |
| This work | branch `Phase3-SME-Prompt-Status` — `80d6a86`, `75f4422`, `8429cfa` |
| Latest run | run02 (2026-11-28), 40/40 prompts |
| Code score | 13 `OK`, 17 `REFUSED`, 0 `BADSQL` |
| Environment blockers | 10 prompts (SP-003 ×6, SP-004 ×4) |
| Open code defects | SP-001, SP-002, SP-005, SP-006 |

**Read this first if you have 60 seconds:** the code work from the F-07x
batch landed — F-077, F-078 and F-082 are all proven fixed by run02. The
run does **not** look better overall (11 → 13 `OK`) because 10 prompts are
simultaneously blocked by two Fusion access problems that have nothing to do
with the code. Do not start by "fixing" procurement or receivables — check
SP-003 and SP-004 first.

## The three things most likely to waste your time

### 1. `/purchaseOrders` returns 0 rows and looks like a correct answer

```
REST  /purchaseOrders  ->  0 rows, HTTP 200
Pod   PO_HEADERS_ALL   ->  18,389
```

No error. The synthesizer says *"No purchase orders found matching the
criteria."* Every procurement prompt scores `ZERO`, and nothing points at
the endpoint. **Check `total_results('/purchaseOrders')` before debugging
any PO prompt.**

### 2. `fastmcp` must be on PATH or the stack silently fails to start

`spire-host.sh` shells out to `fastmcp`. If the venv is not activated:

```
nohup: failed to run command 'fastmcp': No such file or directory
MCP   FAILED port 4001   not bound within 20s
```

Fix:

```bash
export PATH="/home/bhagavan/virtenv/spire/bin:$PATH"
./spire-host.sh --stop && ./spire-host.sh --start dev
```

### 3. Never `pkill -f "spire.mcp_server.server"`

That pattern also matches the user's running stack. It killed the dev MCP
server once during this work. Use `./spire-host.sh --stop` instead.

## Stack

| | |
|---|---|
| Ports | MCP 4001 · API 4002 · UI 4003 (dev) |
| Port config | `SPIRE-PORTS.env` — single source of truth |
| MCP URL for promptkit | `SPIRE_MCP_URL=http://127.0.0.1:4001/mcp/` |
| Python | `/home/bhagavan/virtenv/spire/bin/python` (3.14) |
| Pod | dev49 — `fa-euth-dev49-saasfademo1.ds-fa.oraclepdemos.com` |
| Fusion user | `FUSIONU4` in `personas.yaml` |

The MCP server reads tool definitions and KG carriers at **startup**. After
changing `src/spire/mcp_server/`, `src/spire/kg/`, or the KG seed, restart
the stack or you will test stale code.

## Endpoint health — check before every run

```bash
python -c "
import asyncio
from spire.config import load_persona
from spire.fusion.client import FusionClient
async def m():
    p=load_persona('default_dev')
    async with FusionClient(p) as c:
        for pa in ['/purchaseOrders','/receivablesCustomerAccountActivities',
                   '/suppliers','/invoices','/receivablesInvoices','/standardReceipts']:
            try: print(pa, await c.total_results('/fscmRestApi/resources/11.13.18.05'+pa,''))
            except Exception as e: print(pa,'ERR',type(e).__name__)
asyncio.run(m())"
```

At run02 time: `/purchaseOrders` **0** ⚠️, `/receivablesCustomerAccountActivities`
**403** ⚠️, others healthy. If these change, prompts 1–6 and 24/25/28/30
change with them — for reasons unrelated to any code change.

## KG

| | |
|---|---|
| DB | Oracle 26ai container, `localhost:1521/FREEPDB1`, user `spire` |
| Seed | `scripts/sql/kg_schema.sql` — **23 entities** |
| Rebuild | `python scripts/rebuild_kg.py` |
| Regenerate classifier menu | `python scripts/build_classifier_context.py` |
| Validators | `scripts/validate_kg_schema.py`, `scripts/validate_sql_coverage.py` |

After any seed change: rebuild, regenerate the menu, run both validators.
`tests/test_kg_metadata.py` pins the row counts in five places — see the
repo memory note.

## Running the set

```bash
export PATH="/home/bhagavan/virtenv/spire/bin:$PATH"
./spire-host.sh --start dev

SPIRE_MCP_URL=http://127.0.0.1:4001/mcp/ \
  python scripts/promptkit.py --run \
    --prompt-file prompts/sme_module_a/sme_module_a_litmus.txt \
    --show-parser --show-planner --show-sql --show-synthesizer \
    > evidence/t_<tag>_litmus_run.txt 2>&1
```

**Expect ~50–60 minutes.** One prompt (p20, `aggregate_invoices_by_supplier`)
pages ~25,000 invoices and takes ~15 minutes on its own. A run that "stalls"
at p20 is working, not hung — check `evidence/…` and `logs/mcp.log` for the
`[####....] page N/50` progress line.

Poll with file reads, not terminal sleeps: a shell command that emits
nothing for long enough gets backgrounded and then interrupted, killing the
child.

## Prompt set

```
prompts/sme_module_a/
├── sme_module_a_litmus.txt        # the runnable 40
├── sme_module_a_original.txt      # SME's 40, placeholders intact
├── sme_module_a_expected.md       # PREDICTED status from KG capabilities
└── PROMPT_SHEET_2026-11-21.md     # fill values, readiness at capture
```

**Prediction ≠ observation.** `sme_module_a_expected.md` and the prompt
sheet carry ✅/⚠️/❌ predicted from declared capabilities. They are already
stale — the sheet still says p13 is ❌ ("No InvoiceLine entity/tool") when
run02 answered it. When prediction and observation disagree, the
disagreement *is* the finding; record it, do not silently prefer either.

## What changed this cycle

| Commit | Effect |
|---|---|
| PR #225 (F-077) | AP `InvoiceLine` entity built — p13 works |
| PR #226 (F-076) | AR receipt SQL scoped to REST-visible data |
| PR #227 | SME prompt folders renamed to `sme_qei/` + `sme_module_a/` |
| PR #228 | Bundle manifest reconciled, drift guards re-armed |
| `80d6a86` | `scripts/promptkit.py` — an unprojectable plan no longer aborts the batch |
| `75f4422` | 321 `t_*` evidence files moved out of the root into `evidence/` |
| `8429cfa` | this folder, plus the `plan`-bundle entries and the queue header |

`75f4422` matters more than it looks: the root went from 433 entries to 33,
and one `/evidence/` gitignore rule replaced eleven root-anchored patterns.
Evidence filenames did not change, so any citation in
`docs/fixes/FIX_PLAN.md` still resolves with an `evidence/` prefix.
`scripts/t_s1_f081_emit.py` and `scripts/t_s1_f081_run_sql.sh` take the new
path.

## Known-wrong answers still being produced

Only one: **p13** states *"50 line items"* for an invoice with 184
(**SP-005**). Everything else on the open list is a refusal, which is at
least honest. SP-005 is the highest-priority *correctness* item.

## Next actions, in order

1. **SP-003** — why is `/purchaseOrders` empty? Blocks 6 prompts and makes
   answers silently wrong.
2. **SP-001** — add `supplier_number` to `search_suppliers`. 6 prompts, one
   parameter, REST verified working.
3. **SP-005** — stop claiming a page size is a total (all three line tools).
4. **SP-002** — AR invoice creation-date filter. REST returns 18 rows.
5. **SP-006** — triage the 9 individually; expect p29 to be a correct refusal.
6. **SP-004** — environment only; needs the Fusion grant restored.

Then run03 and add `run03_YYYY-MM-DD_results.md` + a `COMPARISON.md` column.

## How to start the next window

Do not paste this file into the new chat. Point at it — one short line is
enough, and it costs a fraction of a full paste:

```
Resume SPIRE SME prompt work on a new branch off master.
Read docs/plan/sme_prompts_status/HANDOFF.md, then FIX_PLAN.md.
```

The new window reads the files itself, so it gets the *current* text rather
than a snapshot that goes stale the moment you paste it. Paste the content
only if the new window cannot read the workspace.

**Start the next window on a new branch off `master`**, not on
`Phase3-SME-Prompt-Status` — the rules are branch-first, one branch per
unit of work.
