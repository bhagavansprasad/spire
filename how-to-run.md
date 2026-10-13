# How to run Spire

Primary entry point: **`scripts/promptkit.py`** — one tool that runs a single
prompt, runs a whole prompt set end to end, or validates routing (§5).

Commands below are marked:
- 🔵 **ONE-TIME** — run once during setup
- 🟢 **EVERY TIME** — run each session

---

## 1. Setup

🔵 **ONE-TIME**
```bash
source ~/venv/spire/bin/activate
pip install -r requirements.txt
pip install -e .
```

> `pip install -e .` is required — code lives under `src/spire/`, not the
> project root. Without it: `ModuleNotFoundError: No module named 'spire'`.

**Credentials**

🔵 **ONE-TIME**
```bash
cp personas.example.yaml personas.yaml
```

```yaml
default_dev:
  fusion:
    base_url: "https://<your-pod>.oraclepdemos.com"
    username: "<fusion-user>"
    password: "<fusion-pass>"
    auth_type: "basic"
  oracle:
    dsn: "localhost:1521/FREEPDB1"
    username: "spire"
    password: "jnjnuh"
```

> ⚠️ **`personas.yaml` is the single source for all pod and DB
> credentials. Update it whenever a password, pod URL or DB user
> changes** — a rotated Fusion password or a rebuilt DB container will
> otherwise fail at the first call with `ORA-01017` or a 401, with
> nothing else changed. It is gitignored, so nobody else's copy updates
> with yours.

### Oracle Database container

🔵 **ONE-TIME** — pull the image:

```bash
docker pull container-registry.oracle.com/database/free:latest
```

🔵 **ONE-TIME** — create the host data directory:

```bash
mkdir -p ~/oracle_oradata
```

🔵 **ONE-TIME** — create and start the Oracle DB container:

```bash
docker run -d \
  --name oracle26ai_db_spire_iks \
  --restart unless-stopped \
  -p 1521:1521 \
  -e ORACLE_PWD='Abcd1234' \
  -v ~/oracle_oradata:/opt/oracle/oradata \
  container-registry.oracle.com/database/free:latest
```

> `ORACLE_PWD` is the `SYS` / `SYSTEM` password for the container DB — it is
> **not** the `spire` application password.  
> The database and the default PDB `FREEPDB1` are created automatically on
> first startup. First startup can take several minutes.  
> Because of `--restart unless-stopped`, the container **auto-starts on boot**.
> You do **not** need to start it manually each time. Only run
> `docker start oracle26ai_db_spire_iks` if you previously stopped it by hand
> (a manual `docker stop` overrides `unless-stopped` until you start it again).

Confirm the container is up and healthy before creating the `spire` user:

```bash
docker ps
docker inspect --format='{{.State.Health.Status}}' oracle26ai_db_spire_iks
```

Wait until the status is `healthy`. You can also follow the logs:

```bash
docker logs -f oracle26ai_db_spire_iks
```

Look for:

```text
DATABASE IS READY TO USE!
```

🔵 **ONE-TIME** — create the `spire` DB user in `FREEPDB1`:

```bash
docker exec -i oracle26ai_db_spire_iks sqlplus sys/Abcd1234@localhost:1521/FREEPDB1 as sysdba <<'EOF'
CREATE USER spire IDENTIFIED BY "jnjnuh";
GRANT CONNECT, RESOURCE, CREATE VIEW, UNLIMITED TABLESPACE TO spire;
EXIT;
EOF
```

Verify the new user can connect:

```bash
docker exec -it oracle26ai_db_spire_iks sqlplus spire/jnjnuh@localhost:1521/FREEPDB1
```

> Use `sys ... as sysdba`, not `pdbadmin` (`ORA-01031` on this image).  
> `IDENTIFIED BY` must match `oracle.password` in `personas.yaml`.

> If you need to recreate the database from scratch, stop and remove the
> container, clear the host data directory, then run the `docker run` command
> again:
>
> ```bash
> docker stop oracle26ai_db_spire_iks
> docker rm oracle26ai_db_spire_iks
> sudo rm -rf ~/oracle_oradata/*
> # then re-run the docker run command above
> ```
>
> This is destructive — all existing DB data will be lost.

### After rotating credentials

`personas.yaml` is read **once, at startup**, by two services:

- `spire-mcp` — loads Fusion + Oracle creds to build its tool surface
- `spire-api` — loads Fusion creds to display the persona block on `/status`

The **UI does not read it** — it talks to the API, which talks to MCP.

After editing `personas.yaml`:

```bash
# host mode
./spire-host.sh --restart

# docker mode
./spire-docker.sh --restart
```

Then confirm the new values are live:

```bash
curl -s http://127.0.0.1:3002/status | jq .persona
```

The `password_masked` field shows `first2••••last2` of the new value. If
it still matches the old password, the restart did not take — check the
logs:

```bash
./spire-host.sh --status
# or
./spire-docker.sh --logs api
```

**To change the Oracle `spire` password** (the DB user, not the `SYS`
password from §1):

```bash
NEW_ORACLE_PW='<new password>'
docker exec -i oracle26ai_db_spire_iks \
  sqlplus -S sys/Abcd1234@localhost:1521/FREEPDB1 as sysdba <<SQL
ALTER USER spire IDENTIFIED BY "$NEW_ORACLE_PW";
EXIT;
SQL
# then update personas.yaml and --restart
```

Nothing else needs to change — no image rebuild, no `.env` edit, no
ngrok restart. The bind mount means the container sees the file
immediately; only the process needs to re-read it.

---

## 2. LLM keys

Provider via `SPIRE_LLM_PROVIDER` (default `gemini`), model via
`SPIRE_LLM_MODEL`. Each run prints `[llm] provider=… model=…`.

Defaults live in `src/spire/config.py`:

```python
GEMINI_MODEL = "gemini-3.5-flash"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-5"
```

> `2.5-flash` not `2.5-pro`: a fresh `GEMINI_API_KEY` commonly has a
> **0 free-tier quota** for `2.5-pro` (`429 RESOURCE_EXHAUSTED, limit: 0`).

**Gemini** — public API key:

🔵 **ONE-TIME per machine**
```bash
export GEMINI_API_KEY="..."
```

or Vertex AI:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=<project-id>
export GOOGLE_CLOUD_LOCATION=us-central1
gcloud auth application-default login
gcloud auth application-default set-quota-project <project-id>
```

**OpenAI**
```bash
export OPENAI_API_KEY="sk-..."
export SPIRE_LLM_PROVIDER=openai
```

**Anthropic**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SPIRE_LLM_PROVIDER=anthropic
```

> To change a default permanently, edit the constant in `config.py` —
> one file, one place.

### Docker mode

`spire-docker.sh` reads `GEMINI_API_KEY` from `.env` (in the repo root),
not from your shell. Copy `.env.example` and fill it in once:

```bash
cp .env.example .env
$EDITOR .env          # paste GEMINI_API_KEY (and optionally ANTHROPIC / OPENAI)
```

`.env` is gitignored. `personas.yaml` is bind-mounted into the containers
at runtime, so rotating credentials requires only `./spire-docker.sh --restart`.

---

## 3. Run

🟢 **EVERY TIME** — bring up the stack. Two ways, **pick one**. They
cannot run at the same time (same host ports).

**Host mode** — processes on your machine, Python from your venv:

```bash
./spire-host.sh --start              # production: MCP 3001, API 3002, UI 3003
./spire-host.sh --start dev          # dev:        MCP 4001, API 4002, UI 4003
./spire-host.sh --status             # show ports and holder PIDs
./spire-host.sh --stop               # stop these services only
```

**Docker mode** — three containers, one shared image:

```bash
./spire-docker.sh --start            # production (default)
./spire-docker.sh --start dev        # dev
./spire-docker.sh --status           # show state; both modes if no target
./spire-docker.sh --restart          # down, then up -d
./spire-docker.sh --stop             # stop the stack
./spire-docker.sh --logs api         # tail a service
./spire-docker.sh --build            # rebuild the image after a source change
```

Both wrappers read ports from `SPIRE-PORTS.env` (single source of truth),
so `spire-host.sh --start dev` and `spire-docker.sh --start dev` listen
on exactly the same three ports.

> **`spire-host.sh` and `spire-docker.sh` cannot coexist.** Same ports,
> same container names. Stop one before starting the other.

🟢 **EVERY TIME** — Knowledge Graph. Always rebuilt from scratch, never
incrementally:
```bash
python scripts/rebuild_kg.py
```

Optional checks:
```bash
python scripts/print_kg.py
python scripts/print_kg.py --counts-only
```

🟢 **EVERY TIME** — run a prompt:

```bash
python scripts/promptkit.py --run --prompt "List all suppliers in India"
```

> **Restart the MCP server after ANY change under `src/spire/mcp_server/`.**
> Host mode: `./spire-host.sh --restart`.
> Docker mode: `./spire-docker.sh --restart`.

Override provider or model for one command:

```bash
SPIRE_LLM_PROVIDER=openai python scripts/promptkit.py --run --prompt "..."
SPIRE_LLM_MODEL=gemini-2.5-pro python scripts/promptkit.py --run --prompt "..."
```

Exit codes: `0` ok · `2` node error · `4` refusal (out of scope).

> Don't print a raw exit code next to a refusal in a loop — a screen of
> `exit=4` reads as a screen of crashes.

### When the Knowledge Graph changes

The KG lives in the Oracle DB. It is derived from sources in the repo:

| Source | Change triggers rebuild |
|---|---|
| `scripts/sql/kg_schema.sql` | schema change (new table, column, index) |
| `src/spire/planner/registries.py` | entity or tool registration changed |
| `src/spire/nl_parser/vocabulary.py` | business-term vocabulary changed |
| `src/spire/mcp_server/tools/*.py` | a tool was added, removed, or renamed |
| Any KG seed/overlay file | data change (new joins, new patterns) |

Procedure after any of the above:

```bash
# 1. Rebuild — always from scratch, never incremental
python scripts/rebuild_kg.py

# 2. Verify the schema is present and populated
python scripts/print_kg.py --counts-only
#    every table should report 'ok' with a non-zero count

# 3. Re-validate routing — the KG determines which tool handles which
#    intent. A KG change can silently redirect prompts.
python scripts/promptkit.py --validate prompts/supplier/smoke.json

# 4. Restart the stack — MCP reads tool definitions at startup, so a
#    rebuild is not visible to the running service until it restarts.
./spire-host.sh --restart
# or: ./spire-docker.sh --restart
```

If step 2 shows an empty or missing table, the KG build failed midway —
read the rebuild script's output, not just its exit code. `--counts-only`
is the honest gate.

### When to rebuild the Docker image

The image bakes in `src/`, `requirements.txt`, `pyproject.toml`, and
`SPIRE-PORTS.env`. Everything else is either mounted at runtime or
excluded by `.dockerignore`.

| What changed | Action |
|---|---|
| `src/spire/**` (any Python) | rebuild: `./spire-docker.sh --build && ./spire-docker.sh --restart` |
| `requirements.txt` | rebuild |
| `pyproject.toml` | rebuild |
| `Dockerfile` | rebuild |
| `SPIRE-PORTS.env` | rebuild |
| `docker-compose*.yml` | no rebuild — `./spire-docker.sh --stop && ./spire-docker.sh --start` |
| `.env` | `./spire-docker.sh --restart` |
| `personas.yaml` | `./spire-docker.sh --restart` (bind-mounted; no rebuild) |
| `prompts/`, `scripts/`, `docs/`, `tests/` | none — excluded by `.dockerignore` |

Layered caching means a code-only change (`src/` touched, `requirements.txt`
unchanged) usually rebuilds in under 30 seconds. Only a change to
`requirements.txt` triggers the full ~3–5 minute rebuild.

In **dev mode** (`./spire-docker.sh --start dev`) `docker-compose.dev.yml`
bind-mounts `./src` over `/app/src` and runs MCP with `--reload`, so source
edits take effect without a rebuild. Use dev mode while iterating; switch
to production mode for anything you're shipping.

### Raw commands (no wrapper)

If you need to run a single service directly — for a debugger, or to see
raw output without the wrapper's log redirection:

```bash
# Terminal 1 — MCP server
python -m spire.mcp_server.server           # code default: 127.0.0.1:3333

# Terminal 2 — API server
python -m spire.api.server                  # code default: 0.0.0.0:8000

# Terminal 3 — Streamlit UI
spire-ui                                    # code default: 0.0.0.0:8888
```

The code defaults (`3333 / 8000 / 8888`) are what the modules use when no
`SPIRE_MCP_PORT` / `SPIRE_API_PORT` / `SPIRE_UI_PORT` is set. The wrappers
above override them from `SPIRE-PORTS.env`.

---

## 4. Diagnostic flags

**Default is quiet.** `stdout` carries the answer; `stderr` carries
everything else.

```bash
python scripts/promptkit.py --run --prompt "..." 2>/dev/null    # answer alone
```

The flags apply to `promptkit.py --run` (a single `--prompt` or a `.json` corpus). The committed `pyproject.toml` defaults apply too.

| Flag | Shows |
|---|---|
| `--show-parser` | parsed intent, KG menu size, refusal detail |
| `--show-planner` | selected plan, tool, arguments, filters |
| `--show-raw-output` | executor output per step |
| `--show-synthesizer` | response object prior to rendering |
| `--show-tokens` | per-call and end-of-run token counts |
| `--show-timings` | per-stage latency |
| `--show-all` | enable every flag above |

Every flag except `--show-all` has a `--no-` twin:

```bash
python scripts/promptkit.py --run --prompt "..." --show-all --no-show-tokens
```

Progress lines and the summary footer are **never gated** — both on
`stderr`, so `stdout` is unaffected.

The root logger is never touched (langchain, httpx, oracledb and fastmcp
all log at DEBUG).

### Precedence

Later beats earlier:

```
defaults  →  pyproject.toml  →  environment  →  command line
```

Committed default:

```toml
[tool.spire.diagnostics]
show_planner = true
```

Per-machine default:

```bash
export SPIRE_SHOW_PLANNER=1
```

Invalid flag names are reported, not silently ignored.

> `show_all = true` is a **no-op** in a file that already spells out every
> key. Set the individual keys, or use `--show-all` on the CLI.

---

## 5. Prompt sets with promptkit

`scripts/promptkit.py` is the single tool for prompt sets. **JSON** is the one
format; pick exactly one action:

| Action | Input | What it does |
|---|---|---|
| `--generate` | plain `.txt` (one prompt per line) | run each prompt through the router; write a `.json` beside it — each entry `{prompt, module, tool, note}`, the router's ACTUAL choices |
| `--validate` | `.json` | check every prompt still routes to its recorded module + tool. **No execution** — fast |
| `--run` | `.json` | execute each prompt end to end against Fusion AND re-check routing, reporting **which stage** fails (module → intent → tool → plan → execute) |
| `--run --prompt "..."` | — | run one ad-hoc prompt end to end |

Multiple files are accepted per action.

**The JSON format** (one entry per prompt):

```json
{ "prompt": "which vendors are in the US",
  "module": ["supplier"],
  "tool": "search_suppliers",
  "note": "" }
```

- `module` is a list (empty `[]` = nothing matched, i.e. out of scope).
- `tool` is a tool name, `"refuse"` (clean refusal), or `"error"` (a crash).
- `note` is empty on success; carries the reason on refuse/error.

### Generate a corpus (`.txt` -> `.json`)

Write prompts one per line in a `.txt`, then let the router fill in the labels:

```bash
python scripts/promptkit.py --generate prompts/supplier/supplier_smoke.txt
# writes prompts/supplier/smoke.json — REVIEW the module/tool it captured
```

Generate several at once:

```bash
find prompts -name '*.txt' -print0 | xargs -0 python scripts/promptkit.py --generate
```

### Validate routing (fast, no pod)

```bash
python scripts/promptkit.py --validate prompts/supplier/smoke.json
```

A mismatch means the router now routes a prompt differently than the corpus
recorded — a regression to investigate. Deterministic; no MCP server needed.

### Run end to end (with per-stage failure isolation)

The point of the corpus: run every prompt for real and see *where* a failing
one breaks.

```bash
# MCP server must be up (§3)
python scripts/promptkit.py --run --prompt-file prompts/supplier/supplier_smoke.txt
```

Each prompt prints its intent, plan, and answer (like a single run), then the
staged check:

```
------------------------------------------------------------------------
PROMPT: which vendors are in the US
------------------------------------------------------------------------
Intent: ...
Plan: ...
Answer: ...
    module   OK   (['supplier'])
    intent   OK   (Supplier)
    tool     OK   (search_suppliers)
    plan     OK   (1 step(s))
    execute  OK   (25 record(s))
  => PASS: 25 record(s)
```

A failing prompt reports the exact stage — `FAILED AT: planning`,
`FAILED AT: module`, etc. — so you know whether the break is in routing,
intent, tool selection, planning, or the Fusion call, without tracing by hand.
`--run` honours the diagnostics flags (§4) and `pyproject.toml`.

### Overnight runs (all sets, unattended)

`scripts/promptkit_overnight.py` runs promptkit over every set in a manifest,
doing all three phases per set — **generate → validate → run** — one after
another. Each set runs as a separate subprocess with a per-phase timeout, so one
hung or crashing set cannot stop the batch. Built for an unattended run: the
results are there to read in the morning.

The manifest `scripts/manifests/promptkit_sets.yaml` is a top-level `sets:` list of set
names (each resolves to `prompts/<name>.txt` and `<name>.json`). Comment
a line out to skip it; the slow sets (`06_slow`, `08_lifecycle`) are commented
out by default.

**Quick dry run** — generate + validate only, no pod, to confirm it works:

```bash
python scripts/promptkit_overnight.py --skip-run
```

**Full overnight run** — all three phases, end to end. The MCP server must be up
(§3); background it so you can close the terminal:

```bash
# Terminal 1: MCP server running (and backgrounded if you'll close the shell)
nohup python scripts/promptkit_overnight.py \
  > promptkit_overnight_$(date +%Y%m%d).log 2>&1 &
```

**Output** lands in `promptkit_<YYYYMMDD>/`:

```
<name>.txt      full generate + validate + run output for that set
_run_log.txt    one line per set/phase: start, end, duration, exit code
_summary.txt    a compact table (per set/phase: exit code, seconds, status)
```

Read `_summary.txt` first, then open the per-set `.txt` for anything that
errored or looks wrong. Remember the tally is not a verdict (below).

**Useful flags:**

| Flag | Effect |
|---|---|
| `--skip-run` | generate + validate only (fast, no pod) |
| `--skip-generate` | reuse existing `.json`, don't regenerate |
| `--timeout N` | per-phase timeout in seconds (default 3600) |
| `--manifest FILE` / `--outdir DIR` | override the manifest or output dir |

> Exit code per phase: `0` completed · `124` timed out (partial output saved) ·
> other errored (see the set's `.txt`). A non-zero from any phase makes the
> whole run exit non-zero, so an automated caller can tell.

### Reading the results

> **A green tally is not a verdict.** "N/N passed" means nothing errored and
> routing matched the corpus — NOT that every answer is correct. Score each
> prompt into pass / fail / **wrong but did not error**. The third bucket is
> the one that matters. Check specifically for:

- an empty data array behind confident narrative prose
- a page count stated as a total ("25 suppliers" where 421 exist)
- claims about fields absent from the displayed projection
- arithmetic in the narration that is not in the rows
- customer-scoped results that never resolve an `AccountNumber`
- a generalisation true of the first few rows but not the set

### The prompt files

Plain prompt files live in `prompts/` (one prompt per line, `#`
comments). Run `--generate` on them to produce the matching `.json` corpora,
then `--validate` / `--run`. Full inventory in `docs/prompt-sets/SURFACE.md`.

| Path | Purpose |
|---|---|
| `prompts/dipstick/dipstick_smoke.txt` | depth-ordered triage. **Run first** |
| `prompts/supplier/` | supplier module — smoke / verify / exhaust |
| `prompts/payables/` | payables module |
| `prompts/procurement/` | procurement module |
| `prompts/receivables/` | receivables module |
| `prompts/payables_supplier/` (etc.) | cross-module capabilities, top-level folders |
| `prompts/refusals/refusals_smoke.txt` | out-of-scope. **A refusal is a pass** |
| `prompts/columns/columns_verify.txt` | column selection |
| `prompts/sme/sme_testcases.txt` | external QA corpus, verbatim |

> `prompts/scorer/` holds parser-scorer corpora in a different format
> (`EXPECT ||| prompt`) — not for promptkit.

### After you pull

Already set up, just pulled the latest? The KG can change between versions —
rebuild it, confirm counts, then re-validate routing:

```bash
git pull
pip install -e .                       # only if deps changed; harmless otherwise
python scripts/rebuild_kg.py           # always from scratch
python scripts/print_kg.py --counts-only   # all tables should report ok
python scripts/promptkit.py --validate prompts/supplier/smoke.json   # routing still holds?
```

---

## 6. Example prompts

Grouped by the Fusion module the router sends them to. Every one runs end
to end through the full pipeline — router → parser → planner → executor
→ synthesizer.

```bash
# the shape of every run in this section
python scripts/promptkit.py --run --prompt "<prompt>"
```

### Supplier

```bash
python scripts/promptkit.py --run --prompt "Count of suppliers"
python scripts/promptkit.py --run --prompt "Suppliers with their addresses"
```

### Procurement

```bash
python scripts/promptkit.py --run --prompt "Show PO 2144 and its lines"
```

### Payables

```bash
python scripts/promptkit.py --run --prompt "Show me invoices for supplier 1252"
python scripts/promptkit.py --run --prompt "invoices for supplier 1252 over 10000"
```

### Receivables

```bash
python scripts/promptkit.py --run --prompt \
    "Get the AR invoice with CustomerTransactionId 300000248096352"
python scripts/promptkit.py --run --prompt \
    "Show me AR invoices for customer ABC Corporation Americas"
```

### Cross-module

```bash
python scripts/promptkit.py --run --prompt "Top 5 suppliers by spend this year"
```

### Slow — walks ~6,600 suppliers (expect 3–4 minutes)

```bash
python scripts/promptkit.py --run --prompt "Which suppliers have open purchase orders?"
```

### Must refuse cleanly — a clean decline here is correct, not a failure

```bash
python scripts/promptkit.py --run --prompt "show me contract renewals due next quarter"
```

---

## 7. Tests

```bash
python -m pytest -q                  # 886 passed, 18 deselected (~3.5 min)
python -m pytest -q -m integration   # needs MCP server + KG + a provider key
```

> The 18 deselections are deliberate — `addopts = "-m 'not integration'"`
> in `pyproject.toml`. If that count changes unexpectedly, something in
> `pyproject.toml` was overwritten.

---

## 8. Deploying to a cloud instance

The cloud VM is a Linux box with Docker on it. Whatever runs locally under
`spire-docker.sh` runs there identically — there is no cloud-specific
code path. **Source travels via git. Secrets travel out-of-band. The
image is rebuilt on the VM.**

### One-time setup on the VM

```bash
# 1. clone the repo
git clone git@github.com:bhagavansprasad/spire.git
cd spire

# 2. install Docker Engine + Compose plugin (same as local)
mkdir -p ~/.docker/cli-plugins
curl -fSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose

# 3. bring up the Oracle DB container (see §1 for the exact docker run)

# 4. transfer secrets — from your laptop, never via git
#    (run these on your LAPTOP, not on the VM)
scp .env          user@cloud-vm:~/spire/.env
scp personas.yaml user@cloud-vm:~/spire/personas.yaml

# 5. install ngrok agent, copy the authtoken, write ~/.config/ngrok/ngrok.yml

# 6. build + start
./spire-docker.sh --build
./spire-docker.sh --start
./spire-docker.sh --status
```

Those three files — `.env`, `personas.yaml`, ngrok config — live **only on
the VM** and are never tracked by git. They are set once and updated
separately when credentials rotate.

### Every subsequent deploy

On your laptop:

```bash
git add -A
git commit -m "…"
git push
```

On the VM:

```bash
ssh user@cloud-vm
cd ~/spire
git pull
./spire-docker.sh --build        # cached; fast if only src/ changed
./spire-docker.sh --restart
./spire-docker.sh --status       # three healthy containers
curl -s http://127.0.0.1:3002/status | jq .pipeline_ready
```

Then bring up the tunnels:

```bash
ngrok start spire-api-prod spire-ui-prod
# copy the two new public URLs → share with testers
```

That's the whole loop. Rebuild is safe to run every deploy — layered
caching means it completes in seconds unless `requirements.txt` changed.

### What is *not* deployed via git

| File | How it gets to the VM | When to update |
|---|---|---|
| `.env` | `scp` from laptop, one time | when the Gemini key rotates |
| `personas.yaml` | `scp` from laptop, one time | when Fusion or Oracle creds rotate |
| `~/.config/ngrok/ngrok.yml` | manual, one time | when basic-auth passwords change |
| Oracle DB data | inside the DB container on the VM | never — it lives there |
| KG tables | `python scripts/rebuild_kg.py` on the VM | after any pull that touches KG sources |

If the VM points at a **different** Fusion pod or Oracle DB than your laptop,
its `personas.yaml` diverges from yours on purpose. Keep them as two files
that happen to share a name. Never `git`-sync them.

### Rolling back

`git revert` on the laptop + push; on the VM, `git pull && ./spire-docker.sh --build --restart`.
Because the image tag is `spire:local`, there is no tag history — you
roll forward by re-checking-out an older commit and rebuilding. If you
need rollback-by-tag, move to a registry (below).

### When to graduate to a registry

Stay with `git pull + rebuild on the VM` while **all** of the following hold:

- One environment (no separate staging + prod).
- One VM.
- VM rebuilds take under a minute for typical changes.
- Rollback by git-commit is acceptable.

Graduate when any of these break. The move is small: build once on the
laptop or in CI, push to a registry (GHCR is free for private repos;
OCIR if you're on Oracle Cloud), and change the VM's deploy to
`docker compose pull && docker compose up -d`. The compose file itself
barely changes — only the `image:` line stops being `spire:local`.

### When to add CI/CD

Only after the manual loop above starts to hurt. A GitHub Actions
workflow that, on push to `master`, builds the image, pushes to GHCR, and
SSHes into the VM to run `docker compose pull && docker compose up -d`
replaces the manual steps. Same story as the registry graduation: more
moving parts, more to go wrong, worth it only once the manual flow is
genuinely annoying.

### Two gotchas on a cloud VM

1. **VM firewall.** If the VM's security group blocks inbound, only ngrok
   can reach the stack — which is what you want. Loopback bindings
   (`127.0.0.1:…`) mean even without a firewall the ports are not exposed
   to the public internet; the ngrok agent connects to them locally.
2. **Disk space.** The `spire:local` image is ~750 MB, and each rebuild
   leaves a dangling layer behind. Run `docker system prune -f` on the VM
   periodically, or the disk fills after a few dozen deploys.

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'spire'`** — `pip install -e .`
- **`ORA-01017`** — wrong DB password in `personas.yaml`, or the `spire`
  user doesn't exist (§1).
- **`ORA-01031`** creating the user — use `sys ... as sysdba`.
- **`401` from the pod** — Fusion password rotated; update `personas.yaml`
  and the `IKS_FUSION_*` exports. See §1 "After rotating credentials".
- **`429 RESOURCE_EXHAUSTED` / `limit: 0`** — zero free-tier quota for
  that model. Use `gemini-2.5-flash` or switch provider.
- **`429 / credits depleted`** — provider out of credit.
- **`404 not_found: model ...`** — bad `SPIRE_LLM_MODEL`.
- **`DefaultCredentialsError`** — `gcloud auth application-default login`.
- **`No Oracle DB credentials`** — `personas.yaml` oracle block missing
  and no `SPIRE_DB_*` env vars.
- **MCP connection errors** — server not running, or not restarted after
  an `mcp_server/` change.
- **Diagnostics print above the answer when piped** — fixed;
  `diagnostics.answer()` flushes.
- **A whole set refuses with a short entity list** — the KG is stale
  relative to the code. Run `scripts/rebuild_kg.py` before reading
  anything into the results.
- **Docker: `container name "/spire-mcp" is already in use`** — the other
  mode's stack is still up. `./spire-docker.sh --stop` (production) or
  `./spire-docker.sh --stop dev`, then start the one you want.
- **Docker: API `/status` reports `menu load failed: DPY-6005`** — the
  container cannot reach the Oracle DB. Check that `oracle26ai_db_spire_iks`
  is up and that `personas.yaml` uses the container-side DSN; `spire-docker.sh`
  sets `SPIRE_ORACLE_DSN=host.docker.internal:1521/FREEPDB1` by default.

---

## Legacy

```bash
# ask.py — Track A LangGraph agent (1/7 baseline; cleared for removal)
python scripts/ask.py "Show invoices for Lee Supplies after January 2024"
```

> `run_plan.py` was deprecated and deleted. `run_graph.py` still exists but
> `promptkit.py --run --prompt "..."` is the current single-prompt entry point
> (same pipeline, same diagnostics, plus corpus support).
